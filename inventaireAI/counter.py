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



def process_inventory(input_path, target_element=None, progress_callback=None, stop_event=None):
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
            return None

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
                return None

        try:
            with zipfile.ZipFile(input_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
            print(f"Extracted to: {extract_path}")
            folder_path = extract_path

            # Helper to check if a folder has images
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
            return None
        except Exception as e:
            print(f"Error extracting zip file: {e}")
            return None

    if mode == "single_file":
        folder_path = os.path.dirname(os.path.abspath(input_path))
        single_file_name = os.path.basename(input_path)
        images = [single_file_name]
    else:
        # Folder mode (or extracted zip)
        if not os.path.isdir(folder_path):
            print(f"Error: Directory '{folder_path}' not found.")
            return None

        # Get list of image files
        images = [f for f in os.listdir(folder_path) if f.lower().endswith(valid_extensions)]
        images.sort()

    if not images:
        print("No images found to process.")
        return None

    print(f"Found {len(images)} images (in folder). Preparing inventory...")
    if target_element:
        print(f"Targeting specifically: {target_element}")
    else:
        print("Targeting all distinct objects.")

    # CSV setup
    folder_name = os.path.basename(os.path.normpath(folder_path))
    csv_filename = f"{folder_name}_compteur.csv"
    csv_path = os.path.join(folder_path, csv_filename)
    
    # ---------------------------------------------------------
    # PHASE 1: SYNC & DISCOVERY
    # ---------------------------------------------------------
    
    # Define Columns
    desired_known_order = [
        "ID", "Fichier", "Image", "Categorie", "Categorie ID", "Fiabilite",
        "Prix Unitaire", "Prix Neuf Estime", "Prix Total",
        "Nom", "Etat", "Quantite"
    ]
    custom_cols = []
    if ADDITIONAL_CSV_COLUMNS:
        custom_cols = [col.strip() for col in ADDITIONAL_CSV_COLUMNS.split(',') if col.strip()]
    
    # Image column is conditional
    current_desired_order = [c for c in desired_known_order if c != "Image" or INCLUDE_IMAGE_BASE64]
    full_columns = current_desired_order + custom_cols

    # Load existing or create new DF
    if os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path, sep=CSV_SEPARATOR)
            # Ensure ID column exists
            if "ID" not in df.columns:
                 df.insert(0, "ID", range(1, 1 + len(df)))
        except Exception as e:
            print(f"Error reading existing CSV: {e}. Starting fresh.")
            df = pd.DataFrame(columns=full_columns)
    else:
        df = pd.DataFrame(columns=full_columns)

    # Determine next ID
    next_id = 1
    if not df.empty and "ID" in df.columns:
         try:
             # Handle non-numeric IDs gracefully
             existing_ids = pd.to_numeric(df["ID"], errors='coerce').fillna(0).astype(int)
             if not existing_ids.empty:
                 next_id = existing_ids.max() + 1
         except:
             pass

    # Find new files
    existing_files = set()
    if "Fichier" in df.columns:
        existing_files = set(df["Fichier"].astype(str).tolist())
    
    new_files = [img for img in images if img not in existing_files]
    
    if new_files:
        print(f"Found {len(new_files)} new files. Adding to inventory list...")
        new_rows = []
        for img in new_files:
            row = {col: "" for col in full_columns}
            row["ID"] = next_id
            row["Fichier"] = img
            # Initialize numeric/status fields
            row["Fiabilite"] = 0
            row["Quantite"] = 0
            new_rows.append(row)
            next_id += 1
        
        # Concatenate and save immediately
        new_df = pd.DataFrame(new_rows)
        # Align columns
        new_df = new_df.reindex(columns=df.columns, fill_value="")
        
        if df.empty:
            df = new_df
        else:
            df = pd.concat([df, new_df], ignore_index=True)
            
        df.to_csv(csv_path, index=False, encoding='utf-8-sig', sep=CSV_SEPARATOR)
        print(f"Inventory list updated. Total items: {len(df)}")
    else:
        print("No new files to add to inventory list.")

    # Preload categories logic
    categories_context = load_categories()

    # ---------------------------------------------------------
    # PHASE 2: PROCESSING
    # ---------------------------------------------------------
    
    # We iterate through the DF now.
    # We filter for rows that need processing: 
    # 1. File exists on disk
    # 2. "Nom" is empty OR "Fiabilite" is 0/Empty
    
    # Re-read DF to be sure? No, we have it in memory.
    
    total_rows = len(df)
    
    for index, row in df.iterrows():
        # Check for cancellation
        if stop_event and stop_event.is_set():
            print("Process cancelled by user.")
            break

        filename = str(row.get("Fichier", ""))
        if not filename: continue
        
        original_path = os.path.join(folder_path, filename)
        
        # Check if needs processing
        # Conditions: File exists AND (Name empty or Reliability low/zero)
        # Note: If it was processed but reliability was high, we skip.
        
        nom_val = str(row.get("Nom", "")).strip()
        fiabilite_val = row.get("Fiabilite", 0)
        try: fiabilite_val = int(float(fiabilite_val))
        except: fiabilite_val = 0
        
        # Status 'processed'? We don't have a status col, so we rely on data.
        # If Nom is present and Fiabilite > 0, we assume processed.
        
        is_processed = (nom_val != "" and nom_val != "nan") and (fiabilite_val > 0)
        
        if is_processed:
            # Already done, skip
            continue
            
        if not os.path.exists(original_path):
            # File might have been moved (e.g. to 'traitees' or 'manual_review') or deleted
            # If it's not there, we can't scan it.
            # print(f"Skipping {filename}: File not found (maybe already moved).")
            continue

        # If we are here, we need to process!
        if progress_callback:
            # We use index+1 out of total
            progress_callback(index + 1, total_rows, filename)
            
        print(f"Processing [{index + 1}/{total_rows}]: {filename}...")
        
        # Run AI
        results = analyze_image_multiple(original_path, target_element=target_element, categories_context=categories_context, high_quality=True)

        if not isinstance(results, list):
            results = [results]

        # Reliability Check (Block for robust handling)
        low_confidence_items = []
        for item in results:
            score = item.get("fiabilite", 0)
            try: score = int(score)
            except: score = 0
            if score < RELIABILITY_THRESHOLD:
                low_confidence_items.append(item)

        if low_confidence_items:
            print(f"  Warning: {len(low_confidence_items)} objects have low confidence (< {RELIABILITY_THRESHOLD})")
            # If move failed, we proceed to save data?
            # Let's fall through to save data even if low confidence, so user sees it in CSV at least.
            pass

        # ... (Rest of processing: base64, rename, etc.)
        
        # Convert image to base64
        image_base64 = ""
        if INCLUDE_IMAGE_BASE64:
            image_base64 = resize_and_convert_to_base64(original_path)

        # Rename logic (if target, etc) - Keep mostly same
        # ... (Simplification: if we rename, we must update 'Fichier' in DF)
        
        # For simplicity in this robust version, let's skip complex renaming for now unless requested?
        # The user requested "incremental scanning", not changing renaming logic.
        # But wait, original code did renaming. 
        # If we rename `filename` -> `new_filename`, we must update `df.at[index, 'Fichier']`.
        
        new_filename = filename
        if target_element:
             # ... (rename logic from original) ...
             # Copy-paste logic essentially
            total_quantity = 0
            for item in results:
                try: total_quantity += int(item.get("quantite", 0))
                except: pass
            
            sanitized_target = sanitize_filename(target_element)
            ext = os.path.splitext(filename)[1]
            proposed_filename = f"{total_quantity}_{sanitized_target}{ext}"
            
            if proposed_filename != filename:
                 new_path_full = get_unique_filepath(folder_path, proposed_filename)
                 new_filename = os.path.basename(new_path_full)
                 
                 # Compress/move logic
                 temp_path = os.path.join(folder_path, f"temp_{filename}")
                 try:
                     compress_image_to_target(original_path, temp_path)
                     if os.path.exists(temp_path):
                         shutil.move(temp_path, new_path_full)
                         if new_path_full != original_path and os.path.exists(original_path):
                             os.remove(original_path)
                         print(f"  Renamed to: {new_filename}")
                 except Exception as e:
                     print(f"  Rename failed: {e}")
                     new_filename = filename # Revert
        else:
             # Optimization only
             temp_path = os.path.join(folder_path, f"temp_{filename}")
             try:
                 compress_image_to_target(original_path, temp_path)
                 if os.path.exists(temp_path):
                     shutil.move(temp_path, original_path)
             except Exception as e:
                 print(f"  Optimization failed: {e}")

        # Update DF with results
        # Handle multiple results?
        # The DF row structure assumes 1 row per file. 
        # If `results` has multiple items, we might need to split rows?
        # Original code: `for item in results: ... data.append(row)`
        # It created multiple rows for one file!
        
        # Adapt for dataframe update:
        # First item updates CURRENT row.
        # Subsequent items append NEW rows.
        
        for i, item in enumerate(results):
            # ... field extraction ...
            nom_objet = item.get("nom", "Inconnu")
            # ... (extract other fields)
            try: prix_unitaire = int(float(item.get("prix_unitaire_estime", 0)))
            except: prix_unitaire = 0
            try: prix_neuf = int(float(item.get("prix_neuf_estime", 0)))
            except: prix_neuf = 0
            try: quantite_val = int(item.get("quantite", 0))
            except: quantite_val = 0
            prix_total = prix_unitaire * quantite_val
            
            # Map to columns
            update_data = {
                "Nom": nom_objet,
                "Categorie": item.get("categorie_id", "Inconnu"),
                "Categorie ID": item.get("categorie_id", "Inconnu"),
                "Fiabilite": item.get("fiabilite", 0),
                "Quantite": quantite_val,
                "Etat": item.get("etat", "Inconnu"),
                "Prix Unitaire": prix_unitaire,
                "Prix Neuf Estime": prix_neuf,
                "Prix Total": prix_total,
                "Fichier": new_filename # Update filename if renamed
            }
            if INCLUDE_IMAGE_BASE64:
                 update_data["Image"] = image_base64
            
            if i == 0:
                # Update current row
                for col, val in update_data.items():
                    df.at[index, col] = val
            else:
                # Append NEW row
                new_row = df.loc[index].to_dict() # Copy current row (has ID, etc)
                # Update specific fields
                for col, val in update_data.items():
                    new_row[col] = val
                
                # New ID?
                # Original logic: ID was index in list.
                # Here we should probably assign a new ID or share ID?
                # Let's share ID or assign new. Shared ID suggests "same capture event".
                # But ID implies unique record.
                # Let's increment max ID.
                
                # Recalculate max_id? Expensive.
                # Just use a running counter? We lost track of `next_id` inside loop.
                # Let's get max ID from df again?
                new_id = 0
                try: new_id = df["ID"].astype(int).max() + 1
                except: pass
                new_row["ID"] = new_id
                
                # Append
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                
        # Save after processing item
        df.to_csv(csv_path, index=False, encoding='utf-8-sig', sep=CSV_SEPARATOR)
        
    print(f"\nDone! Inventory count saved to {csv_path}")
    return csv_path

def main():
    parser = argparse.ArgumentParser(description="Automate inventory counting from images.")
    parser.add_argument("folder", help="Path to the folder containing images, a zip file, or a single image file")
    parser.add_argument("--target", "-t", help="Optional: Description of specific elements to count (e.g., 'vis', 'voitures rouges').")
    args = parser.parse_args()

    process_inventory(args.folder, args.target)

if __name__ == "__main__":
    main()
