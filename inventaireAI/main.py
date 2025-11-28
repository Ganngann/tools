import os
import pandas as pd
import argparse
from inventory_ai import analyze_image
import shutil

def main():
    parser = argparse.ArgumentParser(description="Automate inventory from images.")
    parser.add_argument("folder", help="Path to the folder containing images")
    args = parser.parse_args()

    folder_path = args.folder
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
    
    # Create a backup/output directory to avoid messing up original files immediately if something goes wrong?
    # Or just rename in place as requested. User requested: "renomer chaque photo en fonction de sa position dans le csv"
    # Let's process first, then rename to be safe.

    for index, filename in enumerate(images, start=1):
        original_path = os.path.join(folder_path, filename)
        new_filename = f"{index}.jpg" # Standardize to jpg or keep original extension? User said "3.jpg"
        # Let's keep original extension for safety or convert? 
        # User example: "3.jpg". Let's assume we rename to {index}.{ext}
        ext = os.path.splitext(filename)[1]
        new_filename = f"{index}{ext}"
        new_path = os.path.join(folder_path, new_filename)

        print(f"Processing [{index}/{len(images)}]: {filename}...")
        
        # Analyze image
        result = analyze_image(original_path)
        
        # Add to data list
        row = {
            "ID": index,
            "Fichier Original": filename,
            "Nouveau Fichier": new_filename,
            "Nom": result.get("nom", "Inconnu"),
            "Categorie": result.get("categorie", "Inconnu"),
            "Quantite": result.get("quantite", 0)
        }
        data.append(row)

        # Rename file
        # Handle case where file already exists (e.g. running script twice)
        if original_path != new_path:
            try:
                os.rename(original_path, new_path)
            except OSError as e:
                print(f"  Warning: Could not rename {filename} to {new_filename}: {e}")
        
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
