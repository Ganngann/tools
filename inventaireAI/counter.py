import os
import datetime
import pandas as pd
import argparse
from inventory_ai import analyze_image_multiple, load_categories
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
            shutil.copy2(source_path, dest_path) # Changed to copy2 for safety in this script
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

    except Exception as e:
        print(f"Error compressing {source_path}: {e}")
        # Fallback: just copy if possible
        if source_path != dest_path and os.path.exists(source_path):
            shutil.copy2(source_path, dest_path)

def main():
    parser = argparse.ArgumentParser(description="Automate inventory counting from images.")
    parser.add_argument("folder", help="Path to the folder containing images, a zip file, or a single image file")
    parser.add_argument("--target", "-t", help="Optional: Description of specific elements to count (e.g., 'vis', 'voitures rouges').")
    args = parser.parse_args()

    input_path = args.folder
    target_element = args.target
    valid_extensions = ('.jpg', '.jpeg', '.png', '.webp')

    # Determine mode: Folder, Zip, or Single File
    mode = "folder"
    folder_path = input_path
    single_file_name = None

    if os.path.isfile(input_path):
        if input_path.lower().endswith('.zip'):
            mode = "zip"
        elif input_path.lower().endswith(valid_extensions):
            mode = "single_file"
        else:
            print(f"Error: File '{input_path}' is not a directory, a zip file, or a supported image.")
            return

    if mode == "zip":
        print(f"Zip file detected: {input_path}")
        extract_path = os.path.splitext(input_path)[0]

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
            with zipfile.ZipFile(input_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
            print(f"Extracted to: {extract_path}")
            folder_path = extract_path

            # Check for single nested folder (often created when zipping a folder)
            def has_images(path):
                return any(f.lower().endswith(valid_extensions) for f in os.listdir(path))

            if not has_images(folder_path):
                items = os.listdir(folder_path)
                if len(items) == 1:
                     potential_subdir = os.path.join(folder_path, items[0])
                     if os.path.isdir(potential_subdir):
                         print(f"Adjusting folder path to nested directory: {potential_subdir}")
                         folder_path = potential_subdir

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

    if mode == "single_file":
        folder_path = os.path.dirname(os.path.abspath(input_path))
        single_file_name = os.path.basename(input_path)
        images = [single_file_name]
    else:
        # Folder mode (or extracted zip)
        if not os.path.isdir(folder_path):
            print(f"Error: Directory '{folder_path}' not found.")
            return

        # Get list of image files
        images = [f for f in os.listdir(folder_path) if f.lower().endswith(valid_extensions)]
        images.sort()

    if not images:
        print("No images found to process.")
        return

    print(f"Found {len(images)} images. Starting processing...")
    if target_element:
        print(f"Targeting specifically: {target_element}")
    else:
        print("Targeting all distinct objects.")

    data = []

    # Preload categories
    categories_context = load_categories()

    for index, filename in enumerate(images, start=1):
        original_path = os.path.join(folder_path, filename)

        print(f"Processing [{index}/{len(images)}]: {filename}...")

        # Analyze image (high_quality=True for counting/detail)
        results = analyze_image_multiple(original_path, target_element=target_element, categories_context=categories_context, high_quality=True)

        if not isinstance(results, list):
            results = [results] # Handle error case returning dict

        # Convert image to base64 (once per image)
        image_base64 = ""
        if INCLUDE_IMAGE_BASE64:
            image_base64 = resize_and_convert_to_base64(original_path)

        # Determine if we should rename based on target
        if target_element:
            # Calculate total quantity for naming
            total_quantity = 0
            for item in results:
                try:
                    total_quantity += int(item.get("quantite", 0))
                except (ValueError, TypeError):
                    pass

            sanitized_target = sanitize_filename(target_element)
            ext = os.path.splitext(filename)[1]
            proposed_filename = f"{total_quantity}_{sanitized_target}{ext}"

            # Check collision
            if proposed_filename != filename:
                new_path_full = get_unique_filepath(folder_path, proposed_filename)
                new_filename = os.path.basename(new_path_full)
            else:
                new_path_full = original_path
                new_filename = filename

            # Compress/Rename to new name safely using a temp file first
            temp_path = os.path.join(folder_path, f"temp_{filename}")
            try:
                # 1. Compress to temp file
                compress_image_to_target(original_path, temp_path)

                # 2. Move temp file to final destination (new_path_full)
                if os.path.exists(temp_path):
                    shutil.move(temp_path, new_path_full)

                    # 3. If we renamed (new path != original), delete original if it still exists
                    # Note: if new_path_full == original_path, we just overwrote it safely via temp, so no delete needed.
                    if new_path_full != original_path and os.path.exists(original_path):
                         os.remove(original_path)

                    filename = new_filename # Update variable for CSV
                    if new_path_full != original_path:
                        print(f"  Renamed to: {filename}")

            except Exception as e:
                 print(f"  Warning: Could not rename {filename} to {new_filename}: {e}")
                 if os.path.exists(temp_path):
                     os.remove(temp_path)
        else:
            # Original behavior: compress in place (temp then move back)
            temp_path = os.path.join(folder_path, f"temp_{filename}")
            try:
                compress_image_to_target(original_path, temp_path)
                # If temp exists and is different from original (it should be different path)
                if os.path.exists(temp_path):
                     # Replace original with compressed
                     shutil.move(temp_path, original_path)
                     # print(f"  Optimized image: {filename}")
            except Exception as e:
                print(f"  Warning: Could not optimize {filename}: {e}")
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        for item in results:
            nom_objet = item.get("nom", "Inconnu")

            prix_unitaire = item.get("prix_unitaire_estime", 0)
            try:
                prix_unitaire = int(float(prix_unitaire))
            except (ValueError, TypeError):
                prix_unitaire = 0

            prix_neuf = item.get("prix_neuf_estime", 0)
            try:
                prix_neuf = int(float(prix_neuf))
            except (ValueError, TypeError):
                prix_neuf = 0

            quantite_val = item.get("quantite", 0)
            try:
                quantite_val = int(quantite_val)
            except (ValueError, TypeError):
                quantite_val = 0

            prix_total = prix_unitaire * quantite_val

            row = {
                "ID": index,
                "Fichier": filename,
                "Nom": nom_objet,
                "Categorie": item.get("categorie", "Inconnu"),
                "Categorie ID": item.get("categorie_id", "Inconnu"),
                "Quantite": quantite_val,
                "Etat": item.get("etat", "Inconnu"),
                "Prix Unitaire": prix_unitaire,
                "Prix Neuf Estime": prix_neuf,
                "Prix Total": prix_total
            }
            if INCLUDE_IMAGE_BASE64:
                row["Image"] = image_base64
            data.append(row)

    # Create DataFrame and save to CSV
    df = pd.DataFrame(data)

    # Add empty columns if configured
    if ADDITIONAL_CSV_COLUMNS:
        additional_cols = [col.strip() for col in ADDITIONAL_CSV_COLUMNS.split(',') if col.strip()]
        for col in additional_cols:
            df[col] = ""

    # Reorder columns
    cols = df.columns.tolist()
    desired_known_order = [
        "ID", "Fichier", "Image", "Categorie", "Categorie ID",
        "Prix Unitaire", "Prix Neuf Estime", "Prix Total",
        "Nom", "Etat", "Quantite"
    ]

    available_known_cols = [c for c in desired_known_order if c in cols]
    custom_cols = [c for c in cols if c not in desired_known_order]

    final_order = available_known_cols + custom_cols
    df = df[final_order]

    # CSV name based on folder name
    folder_name = os.path.basename(os.path.normpath(folder_path))
    csv_filename = f"{folder_name}_compteur.csv"
    csv_path = os.path.join(folder_path, csv_filename)

    df.to_csv(csv_path, index=False, encoding='utf-8-sig', sep=CSV_SEPARATOR)
    print(f"\nDone! Inventory count saved to {csv_path}")

if __name__ == "__main__":
    main()
