import os
import datetime
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
CSV_DECIMAL = os.getenv("CSV_DECIMAL", ".") # Decimal separator for floats
INCLUDE_IMAGE_BASE64 = os.getenv("INCLUDE_IMAGE_BASE64", "True").lower() in ('true', '1', 't')

ADDITIONAL_CSV_COLUMNS = os.getenv("ADDITIONAL_CSV_COLUMNS", "")

# Reliability Settings
RELIABILITY_THRESHOLD = int(os.getenv("RELIABILITY_THRESHOLD", 85))
LOW_CONFIDENCE_ACTION = os.getenv("LOW_CONFIDENCE_ACTION", "move") # 'move' or 'ask'
MANUAL_REVIEW_FOLDER_NAME = os.getenv("MANUAL_REVIEW_FOLDER", "manual_review")
PROCESSED_FOLDER_NAME = "traitees"

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
    
    # Check for context/instructions file
    folder_context = ""
    potential_context_files = ["context.txt", "instructions.txt"]
    for ctx_file in potential_context_files:
        ctx_path = os.path.join(folder_path, ctx_file)
        if os.path.exists(ctx_path):
            try:
                with open(ctx_path, "r", encoding="utf-8") as f:
                    folder_context = f.read().strip()
                print(f"Loaded instructions from {ctx_file}")
                break
            except Exception as e:
                print(f"Error reading {ctx_file}: {e}")
    else:
        # No context file found, ask user
        print("Aucun fichier d'instructions (context.txt) trouvé.")
        user_context_input = input("Entrez des instructions globales pour ce dossier (ou Appuyez sur Entrée pour ignorer) : ").strip()
        if user_context_input:
            folder_context = user_context_input
            # Save it for future runs or record
            ctx_save_path = os.path.join(folder_path, "context.txt")
            try:
                with open(ctx_save_path, "w", encoding="utf-8") as f:
                    f.write(folder_context)
                print(f"Instructions enregistrées dans {ctx_save_path}")
            except Exception as e:
                print(f"Attention: Impossible de sauvegarder context.txt: {e}")
    
    # CSV name based on folder name
    folder_name = os.path.basename(os.path.normpath(folder_path))
    csv_filename = f"{folder_name}.csv"
    csv_path = os.path.join(folder_path, csv_filename) # Save inside folder
    
    # Prepare CSV headers if file doesn't exist
    desired_known_order = [
         "ID", "Fichier Original", "Image", "Categorie", "Categorie ID", "Fiabilite",
         "Prix Unitaire", "Prix Neuf Estime", "Prix Total",
         "Nom", "Etat", "Quantite", "Remarques", "Remarques traitées"
    ]
    custom_cols = []
    if ADDITIONAL_CSV_COLUMNS:
        custom_cols = [col.strip() for col in ADDITIONAL_CSV_COLUMNS.split(',') if col.strip()]

    # We need to determine the full header order to write the header
    # But 'Image' column is conditional.
    current_desired_order = [c for c in desired_known_order if c != "Image" or INCLUDE_IMAGE_BASE64]
    full_columns = current_desired_order + custom_cols

    # Initialize next_id based on existing CSV
    next_id = 1
    if os.path.exists(csv_path):
        try:
            existing_df = pd.read_csv(csv_path, sep=CSV_SEPARATOR)
            
            # Backfill ID if missing (compatibility with legacy files)
            if "ID" not in existing_df.columns:
                print("Legacy CSV detected (missing ID). Generating IDs...")
                existing_df.insert(0, "ID", range(1, 1 + len(existing_df)))
                # Save immediately to upgrade file
                existing_df.to_csv(csv_path, index=False, encoding='utf-8-sig', sep=CSV_SEPARATOR, decimal=CSV_DECIMAL)

            if "ID" in existing_df.columns and not existing_df["ID"].empty:
                 # Handle cases where ID might be string or have NaNs
                 ids = pd.to_numeric(existing_df["ID"], errors='coerce').fillna(0).astype(int)
                 if not ids.empty:
                    next_id = ids.max() + 1
        except Exception as e:
            print(f"Warning: Could not read existing CSV to determine next ID: {e}")
    else:
        # Create empty DataFrame with columns to write header
        pd.DataFrame(columns=full_columns).to_csv(csv_path, index=False, encoding='utf-8-sig', sep=CSV_SEPARATOR, decimal=CSV_DECIMAL)
    
    # Preload categories once to pass to analyze_image
    categories_context = load_categories()

    for index, filename in enumerate(images, start=1):
        original_path = os.path.join(folder_path, filename)

        print(f"Processing [{index}/{len(images)}]: {filename}...")
        
        # Determine Object ID (from filename or new)
        obj_id = None
        # Regex to match ID at the END of filename: ..._ID.ext
        # We look for _(\d+) followed by extension
        match = re.search(r'_(\d+)\.[^.]+$', filename)
        if match:
             try:
                 obj_id = int(match.group(1))
                 print(f"  Existing ID found: {obj_id}")
             except ValueError:
                 pass
        
        if obj_id is None:
             obj_id = next_id
             next_id += 1
             print(f"  Assigned new ID: {obj_id}")

        
        # Initial Analysis
        result = analyze_image(original_path, categories_context=categories_context, folder_context=folder_context)
        
        # Reliability Check
        fiabilite = result.get("fiabilite", 0)
        try:
             fiabilite = int(fiabilite)
        except:
             fiabilite = 0

        action_taken = "proceed" # proceed, skip (moved), ignore (processed despite low score)

        if fiabilite < RELIABILITY_THRESHOLD:
            print(f"  Warning: Low confidence score ({fiabilite} < {RELIABILITY_THRESHOLD})")

            if LOW_CONFIDENCE_ACTION == "ask":
                # Interactive mode
                try:
                    print(f"  Identified: {result.get('nom')} (Qty: {result.get('quantite')})")
                    # Try to open the image for the user
                    try:
                        with Image.open(original_path) as img_preview:
                             img_preview.show()
                    except Exception as e:
                        print(f"  Could not display image: {e}")

                    user_input = input("  [ENTER] Accept, [m] Move to Manual Review, or type a HINT to re-analyze: ").strip()

                    if user_input.lower() == 'm':
                        action_taken = "move"
                    elif user_input == "":
                        action_taken = "proceed"
                    else:
                        # User provided a hint, re-analyze
                        print(f"  Re-analyzing with hint: '{user_input}'...")
                        result = analyze_image(original_path, categories_context=categories_context, user_hint=user_input, folder_context=folder_context)
                        new_score = result.get("fiabilite", 0)
                        print(f"  New Result: {result.get('nom')} (Score: {new_score})")
                        # We assume the user accepts the new result (or we could loop again, but let's keep it simple for now: one retry)
                        action_taken = "proceed"

                except EOFError:
                    # Handle non-interactive environments
                    print("  Non-interactive mode detected, defaulting to move.")
                    action_taken = "move"

            elif LOW_CONFIDENCE_ACTION == "move":
                action_taken = "move"
            else:
                # 'log' or other
                action_taken = "proceed" # Just logged warning above

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
            sanitized_name = "Item"

        ext = os.path.splitext(filename)[1]
        # Filename format: Quantite_Nom_ID.ext
        proposed_filename = f"{quantite}_{sanitized_name}_{obj_id}{ext}"

        if proposed_filename != filename:
            # Create processed folder
            processed_dir = os.path.join(folder_path, PROCESSED_FOLDER_NAME)
            if not os.path.exists(processed_dir):
                os.makedirs(processed_dir)

            new_path = get_unique_filepath(processed_dir, proposed_filename)
            new_filename = os.path.basename(new_path)
        else:
             # Even if name is same, move to processed folder
            processed_dir = os.path.join(folder_path, PROCESSED_FOLDER_NAME)
            if not os.path.exists(processed_dir):
                os.makedirs(processed_dir)
            
            new_path = get_unique_filepath(processed_dir, filename)
            new_filename = os.path.basename(new_path)

        # Convert image to base64
        image_base64 = ""
        if INCLUDE_IMAGE_BASE64:
            image_base64 = resize_and_convert_to_base64(original_path)

        # Add to data list
        prix_unitaire = result.get("prix_unitaire_estime", 0)
        try:
            prix_unitaire = float(prix_unitaire)
        except (ValueError, TypeError):
            prix_unitaire = 0.0

        prix_neuf = result.get("prix_neuf_estime", 0)
        try:
            prix_neuf = float(prix_neuf)
        except (ValueError, TypeError):
            prix_neuf = 0.0

        quantite_val = result.get("quantite", 0)
        try:
            quantite_val = int(quantite_val)
        except (ValueError, TypeError):
            quantite_val = 0

        prix_total = prix_unitaire * quantite_val

        row = {
            "ID": obj_id,
            "Fichier Original": new_filename,
            "Nom": nom_objet,
            "Categorie": result.get("categorie_id", "Inconnu"),
            "Categorie ID": result.get("categorie_id", "Inconnu"),
            "Fiabilite": result.get("fiabilite", 0),
            "Quantite": quantite_val,
            "Etat": result.get("etat", "Inconnu"),
            "Prix Unitaire": prix_unitaire,
            "Prix Neuf Estime": prix_neuf,
            "Prix Total": prix_total,
            "Remarques": "",
            "Remarques traitées": ""
        }
        if INCLUDE_IMAGE_BASE64:
            row["Image"] = image_base64
        # data.append(row)

        # Rename and compress file if needed (this moves it to processed_dir)
        try:
            compress_image_to_target(original_path, new_path)
            if original_path != new_path:
                 print(f"  Processed and moved to: {PROCESSED_FOLDER_NAME}/{new_filename}")
            else:
                 print(f"  Processed file: {new_filename}")
            
            # Save row to CSV (Update or Append)
            try:
                # Read full CSV to check for existence and update
                current_df = pd.DataFrame()
                if os.path.exists(csv_path):
                     # Read all columns as string to avoid type issues, then convert specific ones?
                     # Or just rely on standard pandas inference.
                     current_df = pd.read_csv(csv_path, sep=CSV_SEPARATOR, decimal=CSV_DECIMAL)
                     
                     # Ensure price columns are floats (handling migration from dot to comma or vice versa)
                     price_cols = ["Prix Unitaire", "Prix Neuf Estime", "Prix Total"]
                     for col in price_cols:
                         if col in current_df.columns:
                             # Convert to string, replace comma with dot (universal float), then to numeric
                             current_df[col] = current_df[col].astype(str).str.replace(',', '.', regex=False)
                             current_df[col] = pd.to_numeric(current_df[col], errors='coerce').fillna(0.0)
                     
                     # Ensure all desired columns exist in the loaded CSV (backward compatibility)
                     for col in full_columns:
                         if col not in current_df.columns:
                             current_df[col] = ""
                
                # Create DataFrame for current row
                row_df = pd.DataFrame([row])
                 # Add empty columns if configured
                for col in custom_cols:
                    row_df[col] = ""
                # Ensure correct column order
                row_df = row_df[full_columns]

                if "ID" in current_df.columns:
                     # Check if ID exists
                     # Ensure ID column types match (int)
                     current_df["ID"] = pd.to_numeric(current_df["ID"], errors='coerce').fillna(-1).astype(int)
                     
                     if obj_id in current_df["ID"].values:
                         # Update existing row
                         # We need to align columns before updating
                         # Drop columns in current_df that are not in full_columns? No, keep structure.
                         
                         # Find index
                         idx = current_df.index[current_df["ID"] == obj_id].tolist()[0]
                         
                         # Update columns one by one? Or replace row.
                         for col in full_columns:
                             current_df.at[idx, col] = row_df.iloc[0][col]
                         
                         current_df.to_csv(csv_path, index=False, encoding='utf-8-sig', sep=CSV_SEPARATOR, decimal=CSV_DECIMAL, float_format='%.2f')
                         print(f"  Updated CSV row for ID: {obj_id}")
                     else:
                         # Append new row
                         # Reindex row_df to match current_df columns (handling impromptu columns)
                         # Fill missing columns (the impromptu ones) with empty string
                         row_df = row_df.reindex(columns=current_df.columns, fill_value="")
                         
                         current_df = pd.concat([current_df, row_df], ignore_index=True)
                         
                         current_df.to_csv(csv_path, index=False, encoding='utf-8-sig', sep=CSV_SEPARATOR, decimal=CSV_DECIMAL, float_format='%.2f')
                         print(f"  Appended CSV row for ID: {obj_id}")
                else:
                    # Append (CSV empty or no ID col). This creates the file.
                    row_df.to_csv(csv_path, mode='a', header=False, index=False, encoding='utf-8-sig', sep=CSV_SEPARATOR, decimal=CSV_DECIMAL, float_format='%.2f')
                    print(f"  Appended CSV row for ID: {obj_id}")

            except Exception as e:
                print(f"  Error updating CSV: {e}")

        except Exception as e:
            print(f"  Warning: Could not process {filename} to {new_filename}: {e}")
        
    print(f"\nDone! Inventory saved to {csv_path}")

if __name__ == "__main__":
    main()
