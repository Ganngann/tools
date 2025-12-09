import os
import datetime
import sys
import pandas as pd
import argparse
from inventory_ai import analyze_image, load_categories
import shutil
import base64
import io
import re
import zipfile
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

# Load configuration from environment variables
THUMBNAIL_MAX_WIDTH = int(os.getenv("THUMBNAIL_MAX_WIDTH", 300))
THUMBNAIL_MAX_HEIGHT = int(os.getenv("THUMBNAIL_MAX_HEIGHT", 300))
THUMBNAIL_JPEG_QUALITY = int(os.getenv("THUMBNAIL_JPEG_QUALITY", 70))

COMPRESSION_MAX_SIZE_KB = int(os.getenv("COMPRESSION_MAX_SIZE_KB", 250))
COMPRESSION_INITIAL_MAX_DIM = int(os.getenv("COMPRESSION_INITIAL_MAX_DIM", 2000))
COMPRESSION_START_QUALITY = int(os.getenv("COMPRESSION_START_QUALITY", 85))
COMPRESSION_QUALITY_STEP = int(os.getenv("COMPRESSION_QUALITY_STEP", 10))
COMPRESSION_MIN_QUALITY = int(os.getenv("COMPRESSION_MIN_QUALITY", 20))

CSV_SEPARATOR = os.getenv("CSV_SEPARATOR", ",")
INCLUDE_IMAGE_BASE64 = os.getenv("INCLUDE_IMAGE_BASE64", "True").lower() in ('true', '1', 't')

ADDITIONAL_CSV_COLUMNS = os.getenv("ADDITIONAL_CSV_COLUMNS", "")

# Reliability Settings
RELIABILITY_THRESHOLD = int(os.getenv("RELIABILITY_THRESHOLD", 85))
LOW_CONFIDENCE_ACTION = os.getenv("LOW_CONFIDENCE_ACTION", "move") # 'move' or 'ask'
MANUAL_REVIEW_FOLDER_NAME = os.getenv("MANUAL_REVIEW_FOLDER", "manual_review")

def sanitize_filename(name):
    # Remove invalid characters for Windows/Linux filenames
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = name.strip()
    return name

def get_unique_filepath(folder, filename):
    base, ext = os.path.splitext(filename)
    counter = 1
    new_filename = filename
    while os.path.exists(os.path.join(folder, new_filename)):
        new_filename = f"{base}_{counter}{ext}"
        counter += 1
    return os.path.join(folder, new_filename)

def resize_and_convert_to_base64(image_path, max_size=None):
    if max_size is None:
        max_size = (THUMBNAIL_MAX_WIDTH, THUMBNAIL_MAX_HEIGHT)

    try:
        with Image.open(image_path) as img:
            img.thumbnail(max_size)
            # Convert to RGB if necessary (e.g. for PNG with transparency to JPEG)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=THUMBNAIL_JPEG_QUALITY) # JPEG for size efficiency
            return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except Exception as e:
        print(f"Error converting image to base64: {e}")
        return ""

def compress_image_to_target(source_path, dest_path, max_size_kb=None):
    """
    Compresses an image to be under max_size_kb.
    If already smaller, copies/renames it if needed.
    """
    if max_size_kb is None:
        max_size_kb = COMPRESSION_MAX_SIZE_KB

    target_size_bytes = max_size_kb * 1024

    # If source exists and is already small enough
    if os.path.exists(source_path) and os.path.getsize(source_path) <= target_size_bytes:
        if source_path != dest_path:
            shutil.move(source_path, dest_path)
        return

    # If too big, compress
    quality = COMPRESSION_START_QUALITY
    steps = COMPRESSION_QUALITY_STEP
    min_quality = COMPRESSION_MIN_QUALITY

    try:
        with Image.open(source_path) as img:
            # Start by resizing if huge (e.g. > 4MP)
            if img.width > COMPRESSION_INITIAL_MAX_DIM or img.height > COMPRESSION_INITIAL_MAX_DIM:
                 img.thumbnail((COMPRESSION_INITIAL_MAX_DIM, COMPRESSION_INITIAL_MAX_DIM))

            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            # Loop to reduce quality
            saved = False
            while quality >= min_quality:
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=quality, optimize=True)
                size = buffer.tell()

                if size <= target_size_bytes:
                    with open(dest_path, "wb") as f:
                        f.write(buffer.getvalue())
                    saved = True
                    break

                quality -= steps

            if not saved:
                # If still too big after quality reduction, resize aggressively
                ratio = 0.8
                while True:
                    new_size = (int(img.width * ratio), int(img.height * ratio))
                    resized = img.resize(new_size, Image.Resampling.LANCZOS)

                    buffer = io.BytesIO()
                    resized.save(buffer, format="JPEG", quality=min_quality, optimize=True)
                    size = buffer.tell()

                    if size <= target_size_bytes or new_size[0] < 300:
                        with open(dest_path, "wb") as f:
                            f.write(buffer.getvalue())
                        break
                    ratio *= 0.8

        # If we successfully compressed to dest_path, remove source if different
        if source_path != dest_path and os.path.exists(dest_path):
             os.remove(source_path)

    except Exception as e:
        print(f"Error compressing {source_path}: {e}")
        # Fallback: just move if possible
        if source_path != dest_path and os.path.exists(source_path):
            shutil.move(source_path, dest_path)

def main():
    parser = argparse.ArgumentParser(description="Automate inventory from images.")
    parser.add_argument("folder", help="Path to the folder containing images or a zip file")
    args = parser.parse_args()

    folder_path = args.folder

    # Check for zip file
    if os.path.isfile(folder_path) and folder_path.lower().endswith('.zip'):
        print(f"Zip file detected: {folder_path}")
        extract_path = os.path.splitext(folder_path)[0]

        if os.path.exists(extract_path):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{extract_path}_backup_{timestamp}"
            try:
                os.rename(extract_path, backup_path)
                print(f"Existing folder found. Backed up to: {backup_path}")
            except OSError as e:
                print(f"Error backing up existing folder: {e}")
                return

        try:
            with zipfile.ZipFile(folder_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
            print(f"Extracted to: {extract_path}")
            folder_path = extract_path

            # Check for single nested folder (often created when zipping a folder)
            # or recursively find the first folder with images if the root is empty of images

            # Helper to check if a folder has images
            valid_extensions = ('.jpg', '.jpeg', '.png', '.webp')
            def has_images(path):
                return any(f.lower().endswith(valid_extensions) for f in os.listdir(path))

            if not has_images(folder_path):
                # If root has no images, look for a nested folder
                items = os.listdir(folder_path)

                # Case 1: Single directory inside zip
                if len(items) == 1:
                     potential_subdir = os.path.join(folder_path, items[0])
                     if os.path.isdir(potential_subdir):
                         print(f"Adjusting folder path to nested directory: {potential_subdir}")
                         folder_path = potential_subdir

                # Case 2: If still no images, maybe we should walk to find the first folder with images?
                # This is useful if the zip structure is like:
                # zip_root/
                #   __MACOSX/
                #   actual_folder/
                #      images...

                if not has_images(folder_path):
                     print("No images at root. Searching for images in subdirectories...")
                     found = False
                     for root, dirs, files in os.walk(folder_path):
                         if any(f.lower().endswith(valid_extensions) for f in files):
                             print(f"Found images in: {root}")
                             folder_path = root
                             found = True
                             break
                     if not found:
                         print("Warning: No images found in the zip archive.")

        except zipfile.BadZipFile:
            print("Error: The file is not a valid zip file.")
            return
        except Exception as e:
            print(f"Error extracting zip file: {e}")
            return

    if not os.path.isdir(folder_path):
        print(f"Error: Directory '{folder_path}' not found.")
        return

    # Get list of image files
    valid_extensions = ('.jpg', '.jpeg', '.png', '.webp')
    images = [f for f in os.listdir(folder_path) if f.lower().endswith(valid_extensions)]
    images.sort() # Ensure consistent order

    if not images:
        print("No images found in the specified directory.")
        return

    print(f"Found {len(images)} images. Starting processing...")

    data = []
    
    # Preload categories once to pass to analyze_image
    categories_context = load_categories()

    current_filenames = list(images) # Track filenames as they might change
    moved_files = {} # Track moved files to restore them if we go back: index -> path_in_review

    i = 0
    force_interaction = False # Flag to force prompt when going back

    while i < len(images):
        try:
            index = i + 1
            filename = current_filenames[i]
            original_path = os.path.join(folder_path, filename)

            # Check if file exists (might be missing if we messed up restoration or external deletion)
            if not os.path.exists(original_path):
                 print(f"Warning: File {filename} not found at {original_path}. Skipping.")
                 i += 1
                 continue

            print(f"Processing [{index}/{len(images)}]: {filename}...")

            # Initial Analysis
            result = analyze_image(original_path, categories_context=categories_context)

            # Reliability Check
            fiabilite = result.get("fiabilite", 0)
            try:
                 fiabilite = int(fiabilite)
            except:
                 fiabilite = 0

            action_taken = "proceed" # proceed, skip (moved), ignore (processed despite low score)

            # Determine if we should interact
            should_interact = (fiabilite < RELIABILITY_THRESHOLD and LOW_CONFIDENCE_ACTION == "ask") or force_interaction

            if fiabilite < RELIABILITY_THRESHOLD and not force_interaction:
                print(f"  Warning: Low confidence score ({fiabilite} < {RELIABILITY_THRESHOLD})")

            if should_interact:
                # Interactive mode
                force_interaction = False # Reset flag
                try:
                    print(f"  Identified: {result.get('nom')} (Qty: {result.get('quantite')})")
                    # Try to open the image for the user
                    try:
                        with Image.open(original_path) as img_preview:
                             img_preview.show()
                    except Exception as e:
                        print(f"  Could not display image: {e}")

                    while True: # Loop for valid input
                        user_input = input("  [ENTER] Accept, [m] Move to Manual Review, [b] Back, or type a HINT to re-analyze: ").strip()

                        if user_input.lower() == 'b':
                            if i > 0:
                                print("  <-- Going back to previous image...")
                                i -= 1
                                prev_index = i

                                # Remove data for this index and any subsequent (though there shouldn't be any if we go linearly)
                                # We filter out any row with ID >= prev_index + 1
                                data = [row for row in data if row['ID'] < prev_index + 1]

                                # Check if we need to restore a moved file
                                if prev_index in moved_files:
                                    moved_path = moved_files[prev_index]
                                    restored_name = current_filenames[prev_index]
                                    restored_path = os.path.join(folder_path, restored_name)

                                    if os.path.exists(moved_path):
                                        try:
                                            shutil.move(moved_path, restored_path)
                                            print(f"  Restored {restored_name} from manual review.")
                                            del moved_files[prev_index]
                                        except Exception as e:
                                            print(f"  Error restoring file: {e}")
                                    else:
                                        print(f"  Warning: Could not find file to restore: {moved_path}")

                                force_interaction = True # Force prompt on the previous image
                                action_taken = "back"
                                break
                            else:
                                print("  Already at the first image.")
                                continue

                        elif user_input.lower() == 'm':
                            action_taken = "move"
                            break
                        elif user_input == "":
                            action_taken = "proceed"
                            break
                        else:
                            # User provided a hint, re-analyze
                            print(f"  Re-analyzing with hint: '{user_input}'...")
                            result = analyze_image(original_path, categories_context=categories_context, user_hint=user_input)
                            new_score = result.get("fiabilite", 0)
                            print(f"  New Result: {result.get('nom')} (Score: {new_score})")
                            # Loop again to let user decide on new result
                            continue

                except EOFError:
                    # Handle non-interactive environments
                    print("  Non-interactive mode detected, defaulting to move.")
                    action_taken = "move"

            elif fiabilite < RELIABILITY_THRESHOLD and LOW_CONFIDENCE_ACTION == "move":
                 action_taken = "move"
            else:
                 action_taken = "proceed"

            if action_taken == "back":
                continue # Loop back with new i (decremented)

            if action_taken == "move":
                # Create review folder if needed
                review_dir = os.path.join(folder_path, MANUAL_REVIEW_FOLDER_NAME)
                if not os.path.exists(review_dir):
                    os.makedirs(review_dir)

                dest_path = os.path.join(review_dir, filename)
                try:
                    # Ensure unique filename in review folder
                    if os.path.exists(dest_path):
                         dest_path = get_unique_filepath(review_dir, filename)

                    shutil.move(original_path, dest_path)
                    print(f"  Moved to manual review: {os.path.basename(dest_path)}")

                    moved_files[i] = dest_path # Track for potential restore
                    i += 1
                    # Skip adding to CSV only if move was successful
                    continue
                except Exception as e:
                    print(f"  Error moving file: {e}")
                    print(f"  Proceeding with adding to CSV despite low confidence.")

            # Determine new filename based on object name
            nom_objet = result.get("nom", "Inconnu")
            quantite = result.get("quantite", 0)

            sanitized_name = sanitize_filename(nom_objet)
            if not sanitized_name:
                sanitized_name = f"Item_{index}"

            ext = os.path.splitext(filename)[1]
            proposed_filename = f"{quantite}_{sanitized_name}{ext}"

            if proposed_filename != filename:
                new_path = get_unique_filepath(folder_path, proposed_filename)
                new_filename = os.path.basename(new_path)
            else:
                new_path = original_path
                new_filename = filename

            # Convert image to base64
            image_base64 = ""
            if INCLUDE_IMAGE_BASE64:
                image_base64 = resize_and_convert_to_base64(original_path)

            # Add to data list
            prix_unitaire = result.get("prix_unitaire_estime", 0)
            try:
                prix_unitaire = int(float(prix_unitaire)) # Cast to float first in case it's a string with decimals like "2.0"
            except (ValueError, TypeError):
                prix_unitaire = 0

            prix_neuf = result.get("prix_neuf_estime", 0)
            try:
                prix_neuf = int(float(prix_neuf))
            except (ValueError, TypeError):
                prix_neuf = 0

            quantite_val = result.get("quantite", 0)
            try:
                quantite_val = int(quantite_val)
            except (ValueError, TypeError):
                quantite_val = 0

            prix_total = prix_unitaire * quantite_val

            row = {
                "ID": index,
                "Fichier Original": new_filename,
                "Nom": nom_objet,
                "Categorie": result.get("categorie", "Inconnu"),
                "Categorie ID": result.get("categorie_id", "Inconnu"),
                "Fiabilite": result.get("fiabilite", 0),
                "Quantite": quantite_val,
                "Etat": result.get("etat", "Inconnu"),
                "Prix Unitaire": prix_unitaire,
                "Prix Neuf Estime": prix_neuf,
                "Prix Total": prix_total
            }
            if INCLUDE_IMAGE_BASE64:
                row["Image"] = image_base64
            data.append(row)

            # Rename and compress file if needed
            try:
                compress_image_to_target(original_path, new_path)
                if original_path != new_path:
                    print(f"  Processed and renamed to: {new_filename}")
                    current_filenames[i] = new_filename # Update tracked filename
                else:
                     print(f"  Processed file: {new_filename}")
            except Exception as e:
                print(f"  Warning: Could not process {filename} to {new_filename}: {e}")

            i += 1
        except KeyboardInterrupt:
            print("\n\n--- Paused by User ---")
            while True:
                choice = input("  [c] Continue/Retry, [b] Back, [q] Quit: ").strip().lower()
                if choice == 'c':
                    # i is not incremented yet if caught before i+=1
                    # cleanup data for current attempt (ensure no partial row added)
                    data = [row for row in data if row['ID'] < i + 1]
                    print("  Resuming current image...")
                    break # Restart loop at i
                elif choice == 'b':
                    if i > 0:
                        print("  <-- Going back to previous image...")
                        i -= 1
                        prev_index = i

                        # Remove data
                        data = [row for row in data if row['ID'] < prev_index + 1]

                        # Restore file logic
                        if prev_index in moved_files:
                            moved_path = moved_files[prev_index]
                            restored_name = current_filenames[prev_index]
                            restored_path = os.path.join(folder_path, restored_name)

                            if os.path.exists(moved_path):
                                try:
                                    shutil.move(moved_path, restored_path)
                                    print(f"  Restored {restored_name} from manual review.")
                                    del moved_files[prev_index]
                                except Exception as e:
                                    print(f"  Error restoring file: {e}")

                        force_interaction = True
                        break # Restart loop at i-1
                    else:
                        print("  Already at start.")
                elif choice == 'q':
                    print("Exiting...")
                    sys.exit(0)

    # Create DataFrame and save to CSV
    df = pd.DataFrame(data)
    
    # Add empty columns if configured
    if ADDITIONAL_CSV_COLUMNS:
        additional_cols = [col.strip() for col in ADDITIONAL_CSV_COLUMNS.split(',') if col.strip()]
        for col in additional_cols:
            df[col] = ""

    # Reorder columns: [Standard Cols except Nom, Etat, Quantite], Nom, Etat, Quantite, [Custom Cols]
    cols = df.columns.tolist()
    desired_known_order = [
        "ID", "Fichier Original", "Image", "Categorie", "Categorie ID", "Fiabilite",
        "Prix Unitaire", "Prix Neuf Estime", "Prix Total",
        "Nom", "Etat", "Quantite"
    ]

    available_known_cols = [c for c in desired_known_order if c in cols]
    custom_cols = [c for c in cols if c not in desired_known_order]

    final_order = available_known_cols + custom_cols
    df = df[final_order]

    # CSV name based on folder name
    folder_name = os.path.basename(os.path.normpath(folder_path))
    csv_filename = f"{folder_name}.csv"
    csv_path = os.path.join(folder_path, csv_filename) # Save inside folder or outside? 
    # User said: "encoder le tout dans un csv qui portera le meme nom que le dossier photo"
    # Usually better outside to avoid listing it as a file next time, but user might want it inside.
    # Let's save it INSIDE for now as it's related to the content, or maybe OUTSIDE?
    # "un csv qui portera le meme nom que le dossier photo" -> implies the file itself.
    # Let's save it in the parent directory of the folder to keep the folder just for images?
    # Or inside. Let's put it inside for self-containment, but filter it out in the loop (we already filter by extension).
    
    # Actually, if I rename files inside the loop, and the loop iterates over `images` list which is pre-fetched, it should be fine.
    
    df.to_csv(csv_path, index=False, encoding='utf-8-sig', sep=CSV_SEPARATOR)
    print(f"\nDone! Inventory saved to {csv_path}")

if __name__ == "__main__":
    main()
