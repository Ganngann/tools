import os
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from PIL import Image, ImageTk
import pandas as pd
import argparse
from inventory_ai import analyze_image, load_categories
from dotenv import load_dotenv
import shutil

# Load environment variables
load_dotenv()

CSV_SEPARATOR = os.getenv("CSV_SEPARATOR", ",")
CSV_DECIMAL = os.getenv("CSV_DECIMAL", ".")
PROCESSED_FOLDER_NAME = "traitees"

class ReviewApp:
    def __init__(self, root, csv_path):
        self.root = root
        self.root.title("Inventaire AI - Révision Manuelle")
        self.root.geometry("1200x800")
        
        self.csv_path = csv_path
        self.folder_path = os.path.dirname(os.path.abspath(csv_path))
        self.processed_dir = os.path.join(self.folder_path, PROCESSED_FOLDER_NAME)
        
        self.df = None
        self.review_queue = [] # List of indices to review
        self.current_index = 0
        self.current_rotation = 0
        
        # Load AI Context
        self.categories_context = load_categories() if load_categories else None
        
        self.load_data()
        self.setup_ui()
        self.show_current_item()

    # ... (load_data unchanged) ...

    # ... save_data unchanged ...

    # ... setup_ui unchanged ...

    # ... show_current_item unchanged but resets rotation ...
    
    def show_current_item(self):
        # Reset rotation for new item
        self.current_rotation = 0
        if self.current_index >= len(self.review_queue):
            # ... (end of queue logic) ...
            messagebox.showinfo("Terminé", "Aucun autre élément à réviser !")
            self.root.quit()
            return

        idx = self.review_queue[self.current_index]
        row = self.df.loc[idx]
        
        # Update Title Status
        self.lbl_status.config(text=f"Objet {self.current_index + 1} / {len(self.review_queue)} (ID: {row.get('ID', '?')})")
        
        # Fill fields
        for field, entry in self.fields.items():
            val = row.get(field, "")
            entry.config(state="normal")
            entry.delete(0, tk.END)
            entry.insert(0, str(val))
            if field in ["ID", "Fichier Original", "Fiabilite"]:
                entry.config(state="readonly")

        # Load Image
        filename = row.get("Fichier Original", "")
        if filename:
            image_path = os.path.join(self.processed_dir, str(filename))
            if not os.path.exists(image_path):
                # Try fallback to root
                image_path = os.path.join(self.folder_path, str(filename))
            
            if os.path.exists(image_path):
                print(f"Loading image: {image_path}")
                self.current_image_path = image_path # Store for rotation/rescan
                self.display_image(image_path)
            else:
                print(f"Image not found at: {image_path}")
                self.current_image_path = None
                self.display_placeholder(f"Image introuvable:\n{image_path}")
        else:
            self.current_image_path = None
            self.display_placeholder("Pas de nom de fichier dans le CSV")

    def display_image(self, path):
        try:
            img = Image.open(path)
            
            # Apply Rotation
            if self.current_rotation != 0:
                img = img.rotate(self.current_rotation, expand=True)

            # Resize logic
            win_height = self.root.winfo_height()
            win_width = self.root.winfo_width() // 2
            
            # Simple maintaining aspect ratio
            img.thumbnail((win_width, win_height))
            
            self.tk_img = ImageTk.PhotoImage(img)
            self.image_label.config(image=self.tk_img, text="")
        except Exception as e:
            self.display_placeholder(f"Erreur image: {e}")

    def rotate_image(self):
        if self.current_image_path:
            self.current_rotation = (self.current_rotation - 90) % 360
            self.display_image(self.current_image_path)


    def display_placeholder(self, text):
        self.image_label.config(image="", text=text)

    def get_field_value(self, name):
        return self.fields[name].get()

    def validate_item(self):
        idx = self.review_queue[self.current_index]
        
        # Update DataFrame from fields
        try:
            self.df.at[idx, "Nom"] = self.get_field_value("Nom")
            self.df.at[idx, "Categorie"] = self.get_field_value("Categorie")
            self.df.at[idx, "Etat"] = self.get_field_value("Etat")
            
            # Numeric fields
            try:
                self.df.at[idx, "Quantite"] = int(self.get_field_value("Quantite"))
            except: pass
            
            try:
                pu = float(str(self.get_field_value("Prix Unitaire")).replace(',', '.'))
                self.df.at[idx, "Prix Unitaire"] = pu
            except: pass
            
            try:
                pn = float(str(self.get_field_value("Prix Neuf Estime")).replace(',', '.'))
                self.df.at[idx, "Prix Neuf Estime"] = pn
            except: pass
            
            # Recalculate Total
            try:
                q = float(self.df.at[idx, "Quantite"])
                p = float(self.df.at[idx, "Prix Unitaire"])
                self.df.at[idx, "Prix Total"] = q * p
            except: pass
            
            # Set Reliability to 100
            self.df.at[idx, "Fiabilite"] = 100
            
            self.save_data()
            self.next_item()
            
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de la validation: {e}")

    def delete_item(self):
        if messagebox.askyesno("Confirmer", "Voulez-vous vraiment supprimer cette ligne de l'inventaire ?"):
            idx = self.review_queue[self.current_index]
            self.df = self.df.drop(idx)
            self.save_data()
            
            # Adjust queue issues since index is gone?
            # Actually safely we just move on, next time loaded it's gone
            # But for current session display:
            self.next_item()

    def prev_item(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.show_current_item()
        else:
            messagebox.showinfo("Info", "Vous êtes au début de la liste.")

    def rescan_item(self):
        if not self.current_image_path:
            messagebox.showwarning("Attention", "Pas d'image chargée pour l'analyse.")
            return
            
        hint = simpledialog.askstring("Rescan IA", "Entrez un indice pour l'IA (ex: 'C'est un tournevis'):")
        if hint is None: # Cancelled
            return
            
        try:
            # Show waiting cursor
            self.root.config(cursor="watch")
            self.root.update()
            
            print(f"Rescanning with hint: {hint}")
            result = analyze_image(self.current_image_path, categories_context=self.categories_context, user_hint=hint)
            
            # Update fields directly
            fields_map = {
                "Nom": "nom",
                "Categorie": "categorie", 
                "Etat": "etat",
                "Quantite": "quantite",
                "Prix Unitaire": "prix_unitaire_estime",
                "Prix Neuf Estime": "prix_neuf_estime"
            }
            
            for ui_field, result_key in fields_map.items():
                if result_key in result:
                    val = result[result_key]
                    if result_key == "quantite":
                         try: val = int(float(str(val)))
                         except: pass
                    elif "prix" in result_key:
                         try: val = float(str(val))
                         except: pass
                         
                    entry = self.fields.get(ui_field)
                    if entry:
                        entry.config(state="normal")
                        entry.delete(0, tk.END)
                        entry.insert(0, str(val))
                        
            messagebox.showinfo("Succès", "Analyse terminée ! Vérifiez les valeurs avant de valider.")
            
        except Exception as e:
            messagebox.showerror("Erreur", f"Echec de l'analyse: {e}")
        finally:
            self.root.config(cursor="")

    def next_item(self):
        self.current_index += 1
        self.show_current_item()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Review inventory items.")
    parser.add_argument("csv_file", help="Path to the inventory CSV file")
    args = parser.parse_args()
    
    root = tk.Tk()
    app = ReviewApp(root, args.csv_file)
    root.mainloop()
