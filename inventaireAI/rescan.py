import os
import pandas as pd
import argparse
from inventory_ai import analyze_image, load_categories
from dotenv import load_dotenv

load_dotenv()

CSV_SEPARATOR = os.getenv("CSV_SEPARATOR", ",")
CSV_DECIMAL = os.getenv("CSV_DECIMAL", ".")
PROCESSED_FOLDER_NAME = "traitees"

def rescan_csv(csv_path):
    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found at {csv_path}")
        return

    print(f"Loading {csv_path}...")
    try:
        df = pd.read_csv(csv_path, sep=CSV_SEPARATOR, dtype={'ID': int})
    except Exception as e:
        # Retry without dtype if it fails (e.g. empty file or bad format)
        try:
             df = pd.read_csv(csv_path, sep=CSV_SEPARATOR, decimal=CSV_DECIMAL)
        except Exception as e2:
             return
    
    # Backfill ID if missing (compatibility with legacy files)
    if "ID" not in df.columns:
        print("Legacy CSV detected (missing ID). Generating IDs...")
        df.insert(0, "ID", range(1, 1 + len(df)))
        # Save immediately to upgrade file structure
        df.to_csv(csv_path, index=False, encoding='utf-8-sig', sep=CSV_SEPARATOR, decimal=CSV_DECIMAL)
    
    # Ensure price columns are floats
    price_cols = ["Prix Unitaire", "Prix Neuf Estime", "Prix Total"]
    for col in price_cols:
         if col in df.columns:
             df[col] = df[col].astype(str).str.replace(',', '.', regex=False)
             df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    # Backward compatibility: Add columns if missing.
    columns_added = False
    if "Remarques" not in df.columns:
        print("Column 'Remarques' missing. Adding it.")
        df["Remarques"] = ""
        columns_added = True
    
    if "Remarques traitées" not in df.columns:
        print("Column 'Remarques traitées' missing. Adding it.")
        df["Remarques traitées"] = ""
        columns_added = True

    # Save immediately if we added columns to ensure structure is correct
    if columns_added:
         df.to_csv(csv_path, index=False, encoding='utf-8-sig', sep=CSV_SEPARATOR, decimal=CSV_DECIMAL)
         print("Added missing columns. Please fill 'Remarques' with instructions for items you want to rescan, then run this script again.")
         return

    # Check required columns
    required_cols = ["ID", "Fichier Original"]
    for col in required_cols:
        if col not in df.columns:
            print(f"Error: Missing required column '{col}'")
            return

    # Load categories
    categories_context = load_categories()
    
    folder_path = os.path.dirname(os.path.abspath(csv_path))
    processed_dir = os.path.join(folder_path, PROCESSED_FOLDER_NAME)

    updates_count = 0

    print("Checking for remarks...")
    for index, row in df.iterrows():
        remarks = str(row["Remarques"]) if pd.notna(row["Remarques"]) else ""
        remarks = remarks.strip()
        
        if not remarks:
            continue
            
        filename = row["Fichier Original"]
        # Handle case where filename might be missing or float nan
        if pd.isna(filename) or not str(filename).strip():
             continue

        obj_id = row["ID"]
        
        print(f"Processing ID {obj_id}: {filename}")
        print(f"  Remark: {remarks}")
        
        # Find image
        image_path = os.path.join(processed_dir, filename)
        if not os.path.exists(image_path):
            # Check root (case where images weren't moved or custom setup)
            image_path = os.path.join(folder_path, filename)
            if not os.path.exists(image_path):
                print(f"  Error: Image not found for {filename} at {image_path}")
                continue
        
        # Prepare previous data for context
        previous_data = {
            "nom": row.get("Nom", ""),
            "categorie": row.get("Categorie", ""),
            "quantite": row.get("Quantite", ""),
            "etat": row.get("Etat", ""),
            "prix_unitaire": row.get("Prix Unitaire", "")
        }

        # Re-analyze
        print(f"  Re-analyzing with AI (Remark: '{remarks}')...")
        try:
            result = analyze_image(image_path, categories_context=categories_context, user_hint=remarks, previous_data=previous_data)
            
            # Update row
            # We check if keys exist in result before updating
            if "nom" in result: df.at[index, "Nom"] = result["nom"]
            if "categorie" in result: df.at[index, "Categorie"] = result["categorie"]
            if "categorie_id" in result: df.at[index, "Categorie ID"] = result["categorie_id"]
            if "fiabilite" in result: df.at[index, "Fiabilite"] = result["fiabilite"]
            if "etat" in result: df.at[index, "Etat"] = result["etat"]
            
            # Prices and Qty - robust conversion
            if "quantite" in result:
                 try: df.at[index, "Quantite"] = int(result["quantite"])
                 except: pass

            if "prix_unitaire_estime" in result:
                 try: df.at[index, "Prix Unitaire"] = float(result["prix_unitaire_estime"])
                 except: pass
                 
            if "prix_neuf_estime" in result:
                 try: df.at[index, "Prix Neuf Estime"] = float(result["prix_neuf_estime"])
                 except: pass

            # Update Total
            try:
                qty = float(df.at[index, "Quantite"])
                pu = float(df.at[index, "Prix Unitaire"])
                df.at[index, "Prix Total"] = qty * pu
            except:
                pass

            # Move remark to processed
            current_processed = str(df.at[index, "Remarques traitées"]) if pd.notna(df.at[index, "Remarques traitées"]) else ""
            if current_processed:
                current_processed += " | "
            df.at[index, "Remarques traitées"] = current_processed + remarks
            df.at[index, "Remarques"] = "" # Clear pending remark

            print(f"  Updated: {result.get('nom', 'Unknown')}")
            updates_count += 1
            
        except Exception as e:
            print(f"  Error analyzing image: {e}")
            
    if updates_count > 0:
        try:
            df.to_csv(csv_path, index=False, encoding='utf-8-sig', sep=CSV_SEPARATOR, decimal=CSV_DECIMAL, float_format='%.2f')
            print(f"\nSuccess! Updated {updates_count} rows in {csv_path}")
        except Exception as e:
            print(f"Error saving CSV: {e}")
            print("Make sure the file is not open in another program (like Excel).")
    else:
        print("\nNo entries updated. (Did you add remarks to the 'Remarques' column?)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rescan inventory based on remarks in the CSV.")
    parser.add_argument("csv_file", help="Path to the inventory CSV file")
    args = parser.parse_args()
    
    rescan_csv(args.csv_file)
