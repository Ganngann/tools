import os
import pandas as pd
import argparse
from inventory_ai import analyze_image, load_categories
import shutil
import base64
import io
import re
import zipfile
from PIL import Image

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

def resize_and_convert_to_base64(image_path, max_size=(300, 300)):
    try:
        with Image.open(image_path) as img:
            img.thumbnail(max_size)
            # Convert to RGB if necessary (e.g. for PNG with transparency to JPEG)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=70) # JPEG for size efficiency
            return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except Exception as e:
        print(f"Error converting image to base64: {e}")
        return ""

def compress_image_to_target(source_path, dest_path, max_size_kb=250):
    """
    Compresses an image to be under max_size_kb.
    If already smaller, copies/renames it if needed.
    """
    target_size_bytes = max_size_kb * 1024

    # If source exists and is already small enough
    if os.path.exists(source_path) and os.path.getsize(source_path) <= target_size_bytes:
        if source_path != dest_path:
            shutil.move(source_path, dest_path)
        return

    # If too big, compress
    quality = 85
    steps = 10
    min_quality = 20

    try:
        with Image.open(source_path) as img:
            # Start by resizing if huge (e.g. > 4MP)
            if img.width > 2000 or img.height > 2000:
                 img.thumbnail((2000, 2000))

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

    for index, filename in enumerate(images, start=1):
        original_path = os.path.join(folder_path, filename)

        print(f"Processing [{index}/{len(images)}]: {filename}...")
        
        # Analyze image
        result = analyze_image(original_path, categories_context=categories_context)
        
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
        image_base64 = resize_and_convert_to_base64(original_path)

        # Add to data list
        row = {
            "ID": index,
            "Fichier Original": new_filename,
            "Image": image_base64,
            "Nom": nom_objet,
            "Categorie": result.get("categorie", "Inconnu"),
            "Categorie ID": result.get("categorie_id", "Inconnu"),
            "Quantite": result.get("quantite", 0)
        }
        data.append(row)

        # Rename and compress file if needed
        try:
            compress_image_to_target(original_path, new_path, max_size_kb=250)
            if original_path != new_path:
                print(f"  Processed and renamed to: {new_filename}")
            else:
                 print(f"  Processed file: {new_filename}")
        except Exception as e:
            print(f"  Warning: Could not process {filename} to {new_filename}: {e}")
        
    # Create DataFrame and save to CSV
    df = pd.DataFrame(data)
    
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
    
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"\nDone! Inventory saved to {csv_path}")

if __name__ == "__main__":
    main()
