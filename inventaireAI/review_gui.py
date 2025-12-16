import os
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from PIL import Image, ImageTk
import pandas as pd
import argparse
from inventory_ai import analyze_image, analyze_image_multiple, load_categories
from dotenv import load_dotenv
import shutil
from ui_utils import ToolTip

# Load environment variables
load_dotenv()

CSV_SEPARATOR = os.getenv("CSV_SEPARATOR", ",")
CSV_DECIMAL = os.getenv("CSV_DECIMAL", ".")
PROCESSED_FOLDER_NAME = "traitees"
RETAKE_FOLDER_NAME = "a_refaire"

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
        
        if self.load_data():
            self.setup_ui()
            self.show_current_item()
            
            # Strategy Explanation Popup
            explanation = (
                "Les objets sont affichés du **MOINS fiable au PLUS fiable**.\n"
                "(Les pires erreurs apparaissent en premier)\n\n"
                "CONSEIL :\n"
                "Vous n'êtes pas obligé de tout valider !\n"
                "Corrigez les premières erreurs, et dès que les objets suivants vous semblent corrects,\n"
                "vous pouvez considérer que le reste de l'inventaire est bon et arrêter."
            )
            self.root.after(100, lambda: messagebox.showinfo("Stratégie de Révision", explanation))
            
        else:
            # If loading failed, ensure we exit if verify logic didn't destroy (though logic above says it destroys)
            pass

    def load_data(self):
        if not os.path.exists(self.csv_path):
            messagebox.showerror("Erreur", f"Fichier introuvable: {self.csv_path}")
            self.root.destroy()
            return False
            
        try:
            # Robust loading similar to main.py
            self.df = pd.read_csv(self.csv_path, sep=CSV_SEPARATOR, decimal=CSV_DECIMAL)
            
            # Backfill ID if missing (compatibility with legacy files)
            if "ID" not in self.df.columns:
                print("Legacy CSV detected (missing ID). Generating IDs...")
                self.df.insert(0, "ID", range(1, 1 + len(self.df)))
                # Save immediately to upgrade file
                self.df.to_csv(self.csv_path, index=False, encoding='utf-8-sig', sep=CSV_SEPARATOR, decimal=CSV_DECIMAL, float_format='%.2f')
            
            # Ensure price columns are floats
            price_cols = ["Prix Unitaire", "Prix Neuf Estime", "Prix Total"]
            for col in price_cols:
                if col in self.df.columns:
                     self.df[col] = self.df[col].astype(str).str.replace(',', '.', regex=False)
                     self.df[col] = pd.to_numeric(self.df[col], errors='coerce').fillna(0.0)
            
            # Ensure Commentaire column exists and handle NaNs
            if "Commentaire" not in self.df.columns:
                self.df["Commentaire"] = ""
            else:
                self.df["Commentaire"] = self.df["Commentaire"].fillna("")
            
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
            return False
            
        return True

    def save_data(self):
        try:
            # Atomic Save Strategy
            # 1. Write to a temporary file
            # 2. Rename temporary file to actual file (atomic replace)
            
            temp_path = self.csv_path + ".tmp"
            
            # Recalculate totals if needed (optional logic from before)
            # self.df (already updated in memory)
            
            self.df.to_csv(temp_path, index=False, encoding='utf-8-sig', sep=CSV_SEPARATOR, decimal=CSV_DECIMAL, float_format='%.2f')
            
            # Atomic replace
            if os.path.exists(temp_path):
                try:
                    os.replace(temp_path, self.csv_path)
                    print("Sauvegarde effectuée (Atomic).")
                except OSError as e:
                    # Windows might fail replace if file is locked?
                    # Retry with remove + rename
                    print(f"Atomic replace failed ({e}), trying remove+rename...")
                    if os.path.exists(self.csv_path):
                        os.remove(self.csv_path)
                    os.rename(temp_path, self.csv_path)
                    print("Sauvegarde effectuée (Fallback).")
                    
        except Exception as e:
            messagebox.showerror("Erreur de sauvegarde", f"GRAVE: Impossible de sauvegarder !\n{e}")

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
        
        # Rotation and Rescan Toolbar inside right frame
        self.tools_frame = tk.LabelFrame(self.right_frame, text="Outils & Corrections", padx=10, pady=10)
        self.tools_frame.pack(fill="x", pady=(0, 15))
        
        self.btn_rotate = tk.Button(self.tools_frame, text="🔄 Pivoter", command=self.rotate_image)
        self.btn_rotate.pack(side="left", padx=5)
        ToolTip(self.btn_rotate, "Pivoter l'image de 90° vers la gauche.")
        
        self.btn_rescan = tk.Button(self.tools_frame, text="🧠 Rescan (Indices)", bg="#e2e6ea", command=self.rescan_item)
        self.btn_rescan.pack(side="left", padx=5)
        ToolTip(self.btn_rescan, "Relancer l'IA sur cette image.\nVous pourrez donner un indice (ex: 'C'est un vase') pour aider l'IA.")

        self.btn_multi = tk.Button(self.tools_frame, text="🔢 Scan Multi", bg="#e2e6ea", command=self.scan_multi_item)
        self.btn_multi.pack(side="left", padx=5)
        ToolTip(self.btn_multi, "Utiliser si l'image contient PLUSIEURS objets.\nL'IA essaiera de les séparer en plusieurs lignes d'inventaire.")
        
        self.form_frame = tk.Frame(self.right_frame)
        self.form_frame.pack(fill="x")
        
        # Fields
        self.fields = {}
        
        self.create_field("Commentaire") # Add Commentaire field
        self.create_field("ID", readonly=True)
        self.create_field("Fichier", readonly=True)
        self.create_field("Categorie")
        self.create_field("Nom")
        self.create_field("Etat") # Should be dropdown really, but entry ok
        self.create_field("Quantite")
        self.create_field("Prix Unitaire")
        self.create_field("Prix Neuf Estime")
        
        self.create_field("Fiabilite", readonly=True)
        ToolTip(self.fields["Fiabilite"], "Confiance de l'IA (0-100%).\nSi < 100%, vérifiez bien les infos.\nLe bouton 'Valider' la passera à 100%.")
        
        # Buttons
        # Buttons
        self.btn_frame = tk.Frame(self.right_frame, pady=20)
        self.btn_frame.pack(fill="x")
        
        # Row 1: PRIMARY ACTION (Validate)
        row1 = tk.Frame(self.btn_frame)
        row1.pack(fill="x", pady=5)
        
        self.btn_validate = tk.Button(row1, text="✅ Valider (100%)", bg="#d4edda", font=("Arial", 12, "bold"), height=2, command=self.validate_item)
        self.btn_validate.pack(fill="x")
        ToolTip(self.btn_validate, "Confirmer que les infos sont correctes.\nMet la fiabilité à 100% et passe au suivant.")

        # Row 2: SECONDARY ACTIONS (Comment, Retake, Delete)
        row2 = tk.Frame(self.btn_frame)
        row2.pack(fill="x", pady=5)
        
        self.btn_comment = tk.Button(row2, text="💬 Commenter", bg="#fff3cd", command=self.comment_and_skip_item)
        self.btn_comment.pack(side="left", padx=2, expand=True, fill="x")
        ToolTip(self.btn_comment, "Sauvegarder un commentaire sans valider totalement.\nUtile si vous avez un doute.")

        self.btn_retake = tk.Button(row2, text="📸 À Refaire", bg="#f5c6cb", command=self.mark_as_retake)
        self.btn_retake.pack(side="left", padx=2, expand=True, fill="x")
        ToolTip(self.btn_retake, "Photo ratée ?\nDéplace l'image dans le dossier 'a_refaire' et la retire de la liste.")
        
        self.btn_delete = tk.Button(row2, text="🗑️ Suppr.", bg="#f8d7da", command=self.delete_item)
        self.btn_delete.pack(side="left", padx=2, expand=True, fill="x")
        ToolTip(self.btn_delete, "Supprimer définitivement cet objet de l'inventaire.")

        # Row 3: NAVIGATION (Prev, Next)
        row3 = tk.Frame(self.btn_frame)
        row3.pack(fill="x", pady=10)
        
        self.btn_prev = tk.Button(row3, text="⬅️ Précédent", command=self.prev_item)
        self.btn_prev.pack(side="left", padx=5, expand=True, fill="x")

        self.btn_skip = tk.Button(row3, text="Suivant ➡️", command=self.next_item)
        self.btn_skip.pack(side="left", padx=5, expand=True, fill="x")

        # Status
        self.lbl_status = tk.Label(self.right_frame, text="", fg="blue", font=("Arial", 10, "bold"))
        self.lbl_status.pack(side="bottom", pady=(5, 10))

        # Help Text
        help_text = (
            "Trié par fiabilité croissante (Pires en premier).\n"
            "Fiabilité < 100% = À vérifier. Arrêtez-vous quand c'est bon !"
        )
        self.lbl_help = tk.Label(self.right_frame, text=help_text, fg="#666", font=("Arial", 9), justify="center", bg="#f8f9fa", pady=5)
        self.lbl_help.pack(side="bottom", fill="x", pady=5)

        # Bind Keys
        self.root.bind('<Left>', lambda e: self.prev_item())
        self.root.bind('<Right>', lambda e: self.next_item())

    def load_category_list(self):
        cats = {} # Map ID -> Name
        try:
            csv_path = os.path.join(self.folder_path, "categories.csv")
            if not os.path.exists(csv_path):
                 script_dir = os.path.dirname(os.path.abspath(__file__))
                 csv_path = os.path.join(script_dir, "categories.csv")
            
            if os.path.exists(csv_path):
                cat_df = pd.read_csv(csv_path)
                if "id" in cat_df.columns and "nom" in cat_df.columns:
                    for _, row in cat_df.iterrows():
                        cats[row["id"]] = row["nom"]
        except Exception as e:
            print(f"Error loading categories: {e}")
        return cats

    def create_field(self, name, readonly=False):
        row = tk.Frame(self.form_frame, pady=5)
        row.pack(fill="x")
        lbl = tk.Label(row, text=name, width=20, anchor="w", font=("Arial", 10))
        lbl.pack(side="left")
        
        if name == "Categorie":
            # Use Combobox - Display Names
            self.category_map = self.load_category_list()
            # Sort names for display
            display_values = sorted(list(self.category_map.values()))
            
            entry = ttk.Combobox(row, values=display_values, font=("Arial", 10))
        elif name == "Etat":
            entry = ttk.Combobox(row, values=["Neuf", "Occasion", "Inconnu"], font=("Arial", 10))
        else:
            entry = tk.Entry(row, font=("Arial", 10))
        
        entry.pack(side="left", expand=True, fill="x")
        
        if readonly:
            entry.config(state="readonly")
            
        self.fields[name] = entry

    def _get_reliability_color(self, val):
        try:
            score = float(val)
        except:
            return "white"
            
        # Range: 0-100
        # < 50: Red (#ffcccc)
        # 50-90: Orange/Yellow gradient
        # > 90: Green (#ccffcc)
        
        if score < 50:
            return "#ffcccc" # Light Red
        elif score >= 90:
            return "#ccffcc" # Light Green
        else:
            # Gradient between 50 and 90
            # 50 -> Red/Orange
            # 70 -> Yellow
            # 90 -> Greenish
            
            # Simple approach: 
            # 50-70: Red fading out, Green fading in
            # Gradient simulation with steps
            if score < 70:
                return "#ffeeba" # Orange/Yellow
            elif score < 90:
                 return "#fff3cd" # Light Yellow
            else:
                 return "#ccffcc" # Should not be reached logic-wise but fallback

            else:
                 return "#ccffcc" # Full Green (covered by >=90 check above?)
                 # The >=90 check is above, so this block is for 50 <= score < 90.
                 # So < 90 covers everything remaining.

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
            if pd.isna(val): val = ""
            
            entry.config(state="normal")
            entry.delete(0, tk.END)
            
            if field == "Categorie":
                # Value in DF is now expected to be an ID
                # We want to display the NAME
                cat_id = str(val).strip()
                cat_name = self.category_map.get(cat_id, cat_id) # Fallback to ID if not found
                entry.insert(0, cat_name)
            else:
                entry.insert(0, str(val))
                
            if field in ["ID", "Fichier", "Fichier Original", "Fiabilite"]:
                entry.config(state="readonly")
                
            if field == "Fiabilite":
                color = self._get_reliability_color(val)
                entry.config(bg=color, readonlybackground=color)

        # Load Image
        filename = row.get("Fichier Original", "")
        if not filename:
            filename = row.get("Fichier", "")
            
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
            
            # Simple maintaining aspect ratio
            win_height = self.root.winfo_height()
            win_width = self.root.winfo_width() // 2
            
            # Fallback if window not rendered yet
            if win_height <= 1 or win_width <= 1:
                win_height = 800
                win_width = 600
                
            img.thumbnail((win_width, win_height))
            
            self.tk_img = ImageTk.PhotoImage(img)
            self.image_label.config(image=self.tk_img, text="")
        except Exception as e:
            self.display_placeholder(f"Erreur image: {e}")

    def rotate_image(self):
        if self.current_image_path and os.path.exists(self.current_image_path):
            try:
                img = Image.open(self.current_image_path)
                # Rotate 90 degrees counter-clockwise
                img = img.rotate(90, expand=True)
                img.save(self.current_image_path)
                
                # Refresh display
                self.display_image(self.current_image_path)
                print(f"Image rotated immediately: {self.current_image_path}")
            except Exception as e:
                messagebox.showerror("Erreur", f"Impossible de pivoter l'image: {e}")



    def display_placeholder(self, text):
        self.image_label.config(image="", text=text)

    def comment_and_skip_item(self):
        if self.current_index < len(self.review_queue):
            idx = self.review_queue[self.current_index]
            try:
                # Save comment
                self.df.at[idx, "Commentaire"] = self.get_field_value("Commentaire")
                self.save_data()
                self.next_item()
            except Exception as e:
                messagebox.showerror("Erreur", f"Erreur lors du commentaire: {e}")
        else:
             self.next_item()

    def get_field_value(self, name):
        return self.fields[name].get()

    def validate_item(self):
        idx = self.review_queue[self.current_index]
        
        # Update DataFrame from fields
        try:
            self.df.at[idx, "Nom"] = self.get_field_value("Nom")
            
            # CATEGORY LOGIC: Name -> ID
            cat_name = self.get_field_value("Categorie")
            # Find ID for this name
            cat_id = cat_name # Default
            for cid, cname in self.category_map.items():
                if cname == cat_name:
                    cat_id = cid
                    break
            self.df.at[idx, "Categorie"] = cat_id
            
            self.df.at[idx, "Etat"] = self.get_field_value("Etat")
            self.df.at[idx, "Commentaire"] = self.get_field_value("Commentaire")
            
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
            
            try:
                self.df = self.df.drop(idx)
                
                # Remove from queue to avoid KeyError on navigation
                if idx in self.review_queue:
                    self.review_queue.remove(idx)
                
                # Adjust current index
                if self.current_index >= len(self.review_queue):
                    self.current_index = len(self.review_queue) - 1
                if self.current_index < 0:
                    self.current_index = 0
                    
                self.save_data()
                self.show_current_item()
                
            except Exception as e:
                messagebox.showerror("Erreur", f"Erreur lors de la suppression: {e}")

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
            self._apply_scan_result(result)
                        
            messagebox.showinfo("Succès", "Analyse terminée ! Vérifiez les valeurs avant de valider.")
            
        except Exception as e:
            messagebox.showerror("Erreur", f"Echec de l'analyse: {e}")
        finally:
            self.root.config(cursor="")

    def scan_multi_item(self):
        if not self.current_image_path:
            messagebox.showwarning("Attention", "Pas d'image chargée pour l'analyse.")
            return
            
        hint = simpledialog.askstring("Scan Multi", "Indice optionnel (ex: 'vis', 'boulons'):")
        if hint is None: return

        try:
            self.root.config(cursor="watch")
            self.root.update()
            
            print(f"Multi-scanning with hint: {hint}")
            results = analyze_image_multiple(self.current_image_path, categories_context=self.categories_context, user_hint=hint, target_element=hint)
            
            if not isinstance(results, list):
                results = [results]
                
            if len(results) == 0:
                messagebox.showinfo("Résultat", "Aucun objet détecté.")
                return
                
            # First item updates CURRENT row
            first_item = results[0]
            self._apply_scan_result(first_item)
            
            # Additional items create NEW rows
            new_rows_count = 0
            if len(results) > 1:
                idx = self.review_queue[self.current_index]
                current_row_data = self.df.loc[idx].to_dict() # Base on current to keep ID/Filename/etc mostly
                
                new_ids = []
                
                # Determine next ID
                max_id = 0
                if "ID" in self.df.columns:
                     try: max_id = self.df["ID"].max()
                     except: pass
                
                for i in range(1, len(results)):
                    item = results[i]
                    new_rows_count += 1
                    max_id += 1
                    
                    new_row = current_row_data.copy()
                    new_row["ID"] = max_id
                    new_row["Fiabilite"] = item.get("fiabilite", 0)
                    new_row["Commentaire"] = "Ajouté via Scan Multi"
                    
                    # Apply keys
                    mapping = {
                        "nom": "Nom",
                        "categorie": "Categorie",
                        "etat": "Etat",
                        "quantite": "Quantite",
                        "prix_unitaire_estime": "Prix Unitaire",
                        "prix_neuf_estime": "Prix Neuf Estime"
                    }
                    for res_key, df_key in mapping.items():
                        val = item.get(res_key, "")
                        if df_key in ["Quantite", "Prix Unitaire", "Prix Neuf Estime", "Prix Total"]:
                             try: val = float(str(val))
                             except: pass
                        new_row[df_key] = val
                        
                    # Calculate total
                    try:
                        q = float(new_row.get("Quantite", 0))
                        p = float(new_row.get("Prix Unitaire", 0))
                        new_row["Prix Total"] = q * p
                    except: pass
                    
                    new_ids.append(len(self.df)) # Index of new row
                    self.df = pd.concat([self.df, pd.DataFrame([new_row])], ignore_index=True)

                # Add new items to review queue (insert after current)
                # self.review_queue is a list of INDICES of the DF
                # We just appended rows, so their indices are len(df)-new_rows_count ... len(df)-1
                # But careful, concat reindexes usually if ignore_index=True
                # The indices we want are the last new_rows_count indices of the NEW df
                
                # Re-sort/filter might be complex, let's just append them to queue end for simplicity
                # Or insert them right after current
                current_queue_pos = self.current_index
                
                # The indices of the new rows in the new DF:
                new_indices = list(range(len(self.df) - new_rows_count, len(self.df)))
                
                # Insert details
                self.review_queue[current_queue_pos+1:current_queue_pos+1] = new_indices
                
                self.save_data()

            messagebox.showinfo("Succès", f"Analyse terminée !\n\nObjet courant mis à jour.\n{new_rows_count} nouveaux objets ajoutés à la suite.")

        except Exception as e:
            messagebox.showerror("Erreur", f"Echec du scan multi: {e}")
        finally:
            self.root.config(cursor="")

    def _apply_scan_result(self, result):
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


    def mark_as_retake(self):
        if self.current_index >= len(self.review_queue): return
        
        current_idx = self.review_queue[self.current_index]
        
        if not self.current_image_path or not os.path.exists(self.current_image_path):
             messagebox.showwarning("Attention", "Pas d'image trouvée à déplacer.")
             # Proceed to delete row anyway? Yes.
        
        try:
            filename = None
            if self.current_image_path:
                 filename = os.path.basename(self.current_image_path)
            
            # Identify ALL rows to delete (sharing this image)
            indices_to_drop = [current_idx] 
            if filename:
                 if "Fichier Original" in self.df.columns:
                     indices_to_drop = self.df[self.df["Fichier Original"] == filename].index.tolist()
                 elif "Fichier" in self.df.columns:
                     indices_to_drop = self.df[self.df["Fichier"] == filename].index.tolist()

            # Handle File Operation (MOVE)
            if self.current_image_path and os.path.exists(self.current_image_path):
                 retake_dir = os.path.join(self.folder_path, RETAKE_FOLDER_NAME)
                 if not os.path.exists(retake_dir):
                     os.makedirs(retake_dir)
                 
                 dest_path = os.path.join(retake_dir, filename)
                 
                 # Handle collisions in destination
                 if os.path.exists(dest_path):
                      base, ext = os.path.splitext(filename)
                      import time
                      dest_path = os.path.join(retake_dir, f"{base}_{int(time.time())}{ext}")
                 
                 shutil.move(self.current_image_path, dest_path)
                 print(f"Moved image to retake (cleaning all {len(indices_to_drop)} rows): {dest_path}")
                 self.current_image_path = None # Gone

            # Delete from CSV
            if indices_to_drop:
                self.df = self.df.drop(indices_to_drop)
                
                # Update queue: remove any indices that were just dropped
                # We need to filter self.review_queue
                self.review_queue = [i for i in self.review_queue if i not in indices_to_drop]
                
                # Adjust current index if needed. 
                # If we deleted the current item, self.current_index now points to the *next* item 
                # (because the list shifted left, or rather the list content changed).
                # Wait, review_queue is list of INDICES. 
                # If we remove item at pos X, item at pos X+1 moves to X.
                # So self.current_index is largely still valid (pointing to new item at that slot),
                # unless we were at the end.
                
                if self.current_index >= len(self.review_queue):
                    self.current_index = len(self.review_queue) - 1
                if self.current_index < 0:
                    self.current_index = 0

            self.save_data()
            self.show_current_item()
            
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors du marquage à refaire: {e}")

    def next_item(self):
        if self.current_index < len(self.review_queue) - 1:
            self.current_index += 1
            self.show_current_item()
        else:
            messagebox.showinfo("Info", "Vous êtes au bout de la liste.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Review inventory items.")
    parser.add_argument("csv_file", help="Path to the inventory CSV file")
    args = parser.parse_args()
    
    root = tk.Tk()
    app = ReviewApp(root, args.csv_file)
    root.mainloop()
