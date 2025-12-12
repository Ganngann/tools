import os
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import pandas as pd
import argparse
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
        
        self.load_data()
        self.setup_ui()
        self.show_current_item()

    def load_data(self):
        if not os.path.exists(self.csv_path):
            messagebox.showerror("Erreur", f"Fichier introuvable: {self.csv_path}")
            self.root.destroy()
            return
            
        try:
            # Robust loading similar to main.py
            self.df = pd.read_csv(self.csv_path, sep=CSV_SEPARATOR, decimal=CSV_DECIMAL)
            
            # Ensure price columns are floats
            price_cols = ["Prix Unitaire", "Prix Neuf Estime", "Prix Total"]
            for col in price_cols:
                if col in self.df.columns:
                     self.df[col] = self.df[col].astype(str).str.replace(',', '.', regex=False)
                     self.df[col] = pd.to_numeric(self.df[col], errors='coerce').fillna(0.0)
            
            # Filter items to review: Reliability < 100
            # Sort by reliability ascending (lowest confidence first)
            if "Fiabilite" in self.df.columns:
                self.df["Fiabilite"] = pd.to_numeric(self.df["Fiabilite"], errors='coerce').fillna(0)
                # Get indices of items to review
                review_df = self.df[self.df["Fiabilite"] < 100].sort_values("Fiabilite", ascending=True)
                self.review_queue = review_df.index.tolist()
            else:
                self.review_queue = []
                
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de lire le CSV: {e}")
            self.root.destroy()

    def save_data(self):
        try:
            # Recalculate totals if needed
            self.df.to_csv(self.csv_path, index=False, encoding='utf-8-sig', sep=CSV_SEPARATOR, decimal=CSV_DECIMAL, float_format='%.2f')
            print("Sauvegarde effectuée.")
        except Exception as e:
            messagebox.showerror("Erreur de sauvegarde", f"{e}")

    def setup_ui(self):
        # Layout: Left side for Image, Right side for Form
        
        # --- Left Side (Image) ---
        self.left_frame = tk.Frame(self.root, bg="gray")
        self.left_frame.place(relx=0, rely=0, relwidth=0.5, relheight=1)
        
        self.image_label = tk.Label(self.left_frame, bg="gray")
        self.image_label.pack(expand=True, fill="both")
        
        # --- Right Side (Form) ---
        self.right_frame = tk.Frame(self.root, padx=20, pady=20)
        self.right_frame.place(relx=0.5, rely=0, relwidth=0.5, relheight=1)
        
        # Header
        self.lbl_title = tk.Label(self.right_frame, text="Détails de l'Objet", font=("Arial", 16, "bold"))
        self.lbl_title.pack(pady=(0, 20))
        
        self.form_frame = tk.Frame(self.right_frame)
        self.form_frame.pack(fill="x")
        
        # Fields
        self.fields = {}
        
        self.create_field("ID", readonly=True)
        self.create_field("Fichier Original", readonly=True)
        self.create_field("Categorie")
        self.create_field("Nom")
        self.create_field("Etat") # Should be dropdown really, but entry ok
        self.create_field("Quantite")
        self.create_field("Prix Unitaire")
        self.create_field("Prix Neuf Estime")
        
        self.create_field("Fiabilite", readonly=True)
        
        # Buttons
        self.btn_frame = tk.Frame(self.right_frame, pady=30)
        self.btn_frame.pack(fill="x")
        
        self.btn_validate = tk.Button(self.btn_frame, text="✅ Valider (100%)", bg="#d4edda", font=("Arial", 12), command=self.validate_item)
        self.btn_validate.pack(side="left", padx=5, expand=True, fill="x")
        
        self.btn_skip = tk.Button(self.btn_frame, text="➡️ Passer", font=("Arial", 12), command=self.next_item)
        self.btn_skip.pack(side="left", padx=5, expand=True, fill="x")
        
        self.btn_delete = tk.Button(self.btn_frame, text="🗑️ Supprimer Ligne", bg="#f8d7da", font=("Arial", 12), command=self.delete_item)
        self.btn_delete.pack(side="left", padx=5, expand=True, fill="x")

        # Status
        self.lbl_status = tk.Label(self.right_frame, text="", fg="blue")
        self.lbl_status.pack(side="bottom", pady=10)

    def create_field(self, name, readonly=False):
        row = tk.Frame(self.form_frame, pady=5)
        row.pack(fill="x")
        lbl = tk.Label(row, text=name, width=20, anchor="w", font=("Arial", 10))
        lbl.pack(side="left")
        
        entry = tk.Entry(row, font=("Arial", 10))
        entry.pack(side="left", expand=True, fill="x")
        
        if readonly:
            entry.config(state="readonly")
            
        self.fields[name] = entry

    def show_current_item(self):
        if self.current_index >= len(self.review_queue):
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
                self.display_image(image_path)
            else:
                print(f"Image not found at: {image_path}")
                self.display_placeholder(f"Image introuvable:\n{image_path}")
        else:
            self.display_placeholder("Pas de nom de fichier dans le CSV")

    def display_image(self, path):
        try:
            img = Image.open(path)
            # Resize logic
            win_height = self.root.winfo_height()
            win_width = self.root.winfo_width() // 2
            
            # Simple maintaining aspect ratio
            img.thumbnail((win_width, win_height))
            
            self.tk_img = ImageTk.PhotoImage(img)
            self.image_label.config(image=self.tk_img, text="")
        except Exception as e:
            self.display_placeholder(f"Erreur image: {e}")

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
