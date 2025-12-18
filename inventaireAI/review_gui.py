import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from PIL import Image, ImageTk, ImageDraw
import pandas as pd
import argparse
import ast
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
        self.root.geometry("1200x850")
        
        self.csv_path = csv_path
        self.folder_path = os.path.dirname(os.path.abspath(csv_path))
        self.processed_dir = os.path.join(self.folder_path, PROCESSED_FOLDER_NAME)
        
        self.df = None
        self.review_queue = [] # List of indices to review
        self.current_queue_index = 0
        self.active_df_index = None # The actual index in DF being viewed
        self.current_rotation = 0
        
        self.selection_start = None
        self.selection_rect_id = None
        self.current_selection_coords = None # (x1, y1, x2, y2) in canvas pixels
        self.original_image_object = None # Store PIL image for resizing
        self.current_box_2d = None
        self.show_all_boxes_var = tk.BooleanVar(value=False)
        self.box_map = {} # canvas_id -> df_id

        # Load AI Context
        self.categories_context = load_categories() if load_categories else None
        
        if self.load_data():
            self.setup_ui()
            self.show_current_item()
            
            # Strategy Explanation Popup
            explanation = (
                "Les objets sont affichés du **MOINS fiable au PLUS fiable**.\n"
                "(Les pires erreurs apparaissent en premier)\n\n"
                "NOUVEAU : \n"
                "- Cliquez sur un objet dans la liste (en bas à gauche) pour le voir.\n"
                "- Dessinez un carré rouge pour cibler le rescan.\n"
                "- Redimensionnez la zone d'image/liste avec la barre de séparation.\n"
            )
            self.root.after(100, lambda: messagebox.showinfo("Stratégie de Révision", explanation))
            
        else:
            pass

    def load_data(self):
        if not os.path.exists(self.csv_path):
            messagebox.showerror("Erreur", f"Fichier introuvable: {self.csv_path}")
            self.root.destroy()
            return False
            
        try:
            self.df = pd.read_csv(self.csv_path, sep=CSV_SEPARATOR, decimal=CSV_DECIMAL)
            
            if "ID" not in self.df.columns:
                print("Legacy CSV detected (missing ID). Generating IDs...")
                self.df.insert(0, "ID", range(1, 1 + len(self.df)))
                self.df.to_csv(self.csv_path, index=False, encoding='utf-8-sig', sep=CSV_SEPARATOR, decimal=CSV_DECIMAL, float_format='%.2f')
            
            price_cols = ["Prix Unitaire", "Prix Neuf Estime", "Prix Total"]
            for col in price_cols:
                if col in self.df.columns:
                     self.df[col] = self.df[col].astype(str).str.replace(',', '.', regex=False)
                     self.df[col] = pd.to_numeric(self.df[col], errors='coerce').fillna(0.0)
            
            if "Commentaire" not in self.df.columns:
                self.df["Commentaire"] = ""
            else:
                self.df["Commentaire"] = self.df["Commentaire"].fillna("")
            
            if "Fiabilite" in self.df.columns:
                self.df["Fiabilite"] = pd.to_numeric(self.df["Fiabilite"], errors='coerce').fillna(0)
                # Review everything (including 100% reliable items)
                review_candidates = self.df

                # Determine which column holds the filename
                file_col = "Fichier Original" if "Fichier Original" in self.df.columns else "Fichier"

                # Group by filename and find the minimum reliability for each file
                file_scores = review_candidates.groupby(file_col)["Fiabilite"].min().reset_index()

                # Sort files by their worst (minimum) reliability score
                file_scores = file_scores.sort_values("Fiabilite", ascending=True)

                # The queue is now a list of unique filenames
                self.review_queue = file_scores[file_col].tolist()
            else:
                self.review_queue = []
                
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de lire le CSV: {e}")
            self.root.destroy()
            return False
            
        return True

    def save_data(self):
        try:
            temp_path = self.csv_path + ".tmp"
            self.df.to_csv(temp_path, index=False, encoding='utf-8-sig', sep=CSV_SEPARATOR, decimal=CSV_DECIMAL, float_format='%.2f')
            
            if os.path.exists(temp_path):
                try:
                    os.replace(temp_path, self.csv_path)
                except OSError as e:
                    if os.path.exists(self.csv_path):
                        os.remove(self.csv_path)
                    os.rename(temp_path, self.csv_path)
                    
        except Exception as e:
            messagebox.showerror("Erreur de sauvegarde", f"GRAVE: Impossible de sauvegarder !\n{e}")

    def setup_ui(self):
        # --- Left Side (PanedWindow) ---
        self.left_frame = tk.Frame(self.root, bg="gray")
        self.left_frame.place(relx=0, rely=0, relwidth=0.5, relheight=1)
        
        # PanedWindow for resizing
        self.paned_window = tk.PanedWindow(self.left_frame, orient=tk.VERTICAL, bg="gray", sashwidth=5, sashrelief="raised")
        self.paned_window.pack(fill="both", expand=True)

        # 1. Canvas Frame (Top)
        self.canvas_frame = tk.Frame(self.paned_window, bg="gray")
        self.image_canvas = tk.Canvas(self.canvas_frame, bg="gray", cursor="cross")
        self.image_canvas.pack(fill="both", expand=True)

        # Bind Mouse Events
        self.image_canvas.bind("<Button-1>", self.on_mouse_down)
        self.image_canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.image_canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        # Bind Resize Event
        self.image_canvas.bind("<Configure>", self.on_canvas_resize)

        self.paned_window.add(self.canvas_frame, stretch="always")

        # 2. Sibling List Frame (Bottom)
        self.sibling_frame = tk.Frame(self.paned_window, bg="#f0f0f0")

        lbl_siblings = tk.Label(self.sibling_frame, text="Objets détectés dans la même image :", font=("Arial", 10, "bold"), bg="#f0f0f0")
        lbl_siblings.pack(anchor="w", padx=5, pady=2)

        cols = ("ID", "Nom", "Qte", "Etat", "Fiab")
        self.sibling_tree = ttk.Treeview(self.sibling_frame, columns=cols, show='headings', selectmode="browse")
        self.sibling_tree.heading("ID", text="ID")
        self.sibling_tree.heading("Nom", text="Nom")
        self.sibling_tree.heading("Qte", text="Qté")
        self.sibling_tree.heading("Etat", text="État")
        self.sibling_tree.heading("Fiab", text="Fiab.")

        self.sibling_tree.column("ID", width=40, anchor="center")
        self.sibling_tree.column("Nom", width=160, anchor="w")
        self.sibling_tree.column("Qte", width=40, anchor="center")
        self.sibling_tree.column("Etat", width=80, anchor="center")
        self.sibling_tree.column("Fiab", width=50, anchor="center")

        # Bind Selection Event
        self.sibling_tree.bind("<<TreeviewSelect>>", self.on_sibling_select)
        self.sibling_tree.bind("<Motion>", self.on_tree_hover)

        vsb = ttk.Scrollbar(self.sibling_frame, orient="vertical", command=self.sibling_tree.yview)
        self.sibling_tree.configure(yscrollcommand=vsb.set)

        self.sibling_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.paned_window.add(self.sibling_frame, stretch="never", height=200) # Initial height
        
        # --- Right Side (Form) ---
        self.right_frame = tk.Frame(self.root, padx=20, pady=20)
        self.right_frame.place(relx=0.5, rely=0, relwidth=0.5, relheight=1)
        
        self.lbl_title = tk.Label(self.right_frame, text="Détails de l'Objet", font=("Arial", 16, "bold"))
        self.lbl_title.pack(pady=(0, 20))
        
        self.tools_frame = tk.LabelFrame(self.right_frame, text="Outils & Corrections", padx=10, pady=10)
        self.tools_frame.pack(fill="x", pady=(0, 15))
        
        self.btn_rotate = tk.Button(self.tools_frame, text="🔄 Pivoter G", command=lambda: self.rotate_image("left"))
        self.btn_rotate.pack(side="left", padx=5)
        ToolTip(self.btn_rotate, "Pivoter l'image de 90° vers la gauche.")

        self.btn_rotate_right = tk.Button(self.tools_frame, text="Pivoter D 🔄", command=lambda: self.rotate_image("right"))
        self.btn_rotate_right.pack(side="left", padx=5)
        ToolTip(self.btn_rotate_right, "Pivoter l'image de 90° vers la droite.")
        
        self.chk_boxes = tk.Checkbutton(self.tools_frame, text="Voir tous les carrés", variable=self.show_all_boxes_var, command=lambda: self.display_image(None, self.current_box_2d))
        self.chk_boxes.pack(side="left", padx=5)

        self.btn_rescan = tk.Button(self.tools_frame, text="🧠 Rescan (Zone)", bg="#e2e6ea", command=self.rescan_item)
        self.btn_rescan.pack(side="left", padx=5)
        ToolTip(self.btn_rescan, "Relancer l'IA.\nSi vous avez dessiné un carré rouge, l'IA analysera UNIQUEMENT cette zone.\nSinon, elle re-scanne toute l'image.")

        self.btn_multi = tk.Button(self.tools_frame, text="🔢 Scan Multi", bg="#e2e6ea", command=self.scan_multi_item)
        self.btn_multi.pack(side="left", padx=5)
        ToolTip(self.btn_multi, "Utiliser si l'image contient PLUSIEURS objets.\nL'IA essaiera de les séparer en plusieurs lignes d'inventaire.")
        
        self.form_frame = tk.Frame(self.right_frame)
        self.form_frame.pack(fill="x")
        
        self.fields = {}
        self.create_field("Commentaire")
        self.create_field("ID", readonly=True)
        self.create_field("Fichier", readonly=True)
        self.create_field("Categorie")
        self.create_field("Nom")
        self.create_field("Etat")
        self.create_field("Quantite")
        self.create_field("Prix Unitaire")
        self.create_field("Prix Neuf Estime")
        self.create_field("Fiabilite", readonly=True)
        ToolTip(self.fields["Fiabilite"], "Confiance de l'IA (0-100%).\nSi < 100%, vérifiez bien les infos.\nLe bouton 'Valider' la passera à 100%.")
        
        self.btn_frame = tk.Frame(self.right_frame, pady=20)
        self.btn_frame.pack(fill="x")
        
        row1 = tk.Frame(self.btn_frame)
        row1.pack(fill="x", pady=5)
        self.btn_validate = tk.Button(row1, text="✅ Valider (100%)", bg="#d4edda", font=("Arial", 12, "bold"), height=2, command=self.validate_item)
        self.btn_validate.pack(fill="x")

        row2 = tk.Frame(self.btn_frame)
        row2.pack(fill="x", pady=5)
        self.btn_comment = tk.Button(row2, text="💬 Commenter", bg="#fff3cd", command=self.comment_and_skip_item)
        self.btn_comment.pack(side="left", padx=2, expand=True, fill="x")
        self.btn_retake = tk.Button(row2, text="📸 À Refaire", bg="#f5c6cb", command=self.mark_as_retake)
        self.btn_retake.pack(side="left", padx=2, expand=True, fill="x")
        self.btn_delete = tk.Button(row2, text="🗑️ Suppr.", bg="#f8d7da", command=self.delete_item)
        self.btn_delete.pack(side="left", padx=2, expand=True, fill="x")

        row3 = tk.Frame(self.btn_frame)
        row3.pack(fill="x", pady=10)
        self.btn_prev = tk.Button(row3, text="⬅️ Précédent", command=self.prev_item)
        self.btn_prev.pack(side="left", padx=5, expand=True, fill="x")
        self.btn_skip = tk.Button(row3, text="Suivant ➡️", command=self.next_item)
        self.btn_skip.pack(side="left", padx=5, expand=True, fill="x")

        self.lbl_status = tk.Label(self.right_frame, text="", fg="blue", font=("Arial", 10, "bold"))
        self.lbl_status.pack(side="bottom", pady=(5, 10))

        self.lbl_help = tk.Label(self.right_frame, text="Trié par fiabilité croissante (Pires en premier).", fg="#666", font=("Arial", 9), justify="center", bg="#f8f9fa", pady=5)
        self.lbl_help.pack(side="bottom", fill="x", pady=5)

        self.root.bind('<Left>', lambda e: self.prev_item())
        self.root.bind('<Right>', lambda e: self.next_item())

    # --- Mouse Selection Logic ---
    def on_mouse_down(self, event):
        self.selection_start = (event.x, event.y)
        if self.selection_rect_id:
            self.image_canvas.delete(self.selection_rect_id)
            self.selection_rect_id = None
            self.current_selection_coords = None

    def on_mouse_drag(self, event):
        if not self.selection_start: return
        x0, y0 = self.selection_start
        x1, y1 = event.x, event.y
        if self.selection_rect_id:
            self.image_canvas.coords(self.selection_rect_id, x0, y0, x1, y1)
        else:
            self.selection_rect_id = self.image_canvas.create_rectangle(x0, y0, x1, y1, outline="red", width=3)

    def on_mouse_up(self, event):
        if not self.selection_start: return
        x0, y0 = self.selection_start
        x1, y1 = event.x, event.y
        min_x, max_x = min(x0, x1), max(x0, x1)
        min_y, max_y = min(y0, y1), max(y0, y1)
        if (max_x - min_x) > 10 and (max_y - min_y) > 10:
            self.current_selection_coords = (min_x, min_y, max_x, max_y)
        else:
            if self.selection_rect_id:
                self.image_canvas.delete(self.selection_rect_id)
                self.selection_rect_id = None
                self.current_selection_coords = None

    # --- Hover Handling ---
    def on_box_enter(self, item_id):
        # Highlight in tree
        for item in self.sibling_tree.get_children():
            vals = self.sibling_tree.item(item, 'values')
            if str(vals[0]) == str(item_id):
                # We use a tag to highlight
                self.sibling_tree.item(item, tags=("current", "hovered"))
                break

    def on_box_leave(self, event):
        # Restore tags
        current_id = self.df.at[self.active_df_index, "ID"] if self.active_df_index is not None else None
        for item in self.sibling_tree.get_children():
            vals = self.sibling_tree.item(item, 'values')
            if str(vals[0]) == str(current_id):
                 self.sibling_tree.item(item, tags=("current",))
            else:
                 self.sibling_tree.item(item, tags=())

    def on_tree_hover(self, event):
        item_id = self.sibling_tree.identify_row(event.y)
        if hasattr(self, '_last_hovered_item') and self._last_hovered_item == item_id:
            return
        self._last_hovered_item = item_id

        # Reset canvas boxes first
        for rect_id in self.box_map:
             # Check if it's the active one
             linked_id = self.box_map[rect_id]
             current_id = self.df.at[self.active_df_index, "ID"] if self.active_df_index is not None else None
             if str(linked_id) == str(current_id):
                 self.image_canvas.itemconfig(rect_id, width=3, outline="#00ff00")
             else:
                 self.image_canvas.itemconfig(rect_id, width=1, outline="blue")

        if not item_id: return
        vals = self.sibling_tree.item(item_id, 'values')
        if not vals: return

        obj_id = vals[0]

        # Highlight box on canvas
        target_rect = None
        for rect_id, linked_id in self.box_map.items():
            if str(linked_id) == str(obj_id):
                target_rect = rect_id
                break

        if target_rect:
             self.image_canvas.itemconfig(target_rect, width=4, outline="yellow")

    # --- Resize Handling ---
    def on_canvas_resize(self, event):
        # Debounce or just redraw? Just redraw for now
        if self.original_image_object:
             # Use current box_2d to redraw correctly
             self.display_image(None, self.current_box_2d)

    def update_status(self, message):
        """Updates the status label and forces a UI refresh to show progress."""
        self.lbl_status.config(text=message, fg="red")
        self.root.update()

    # --- Sibling Navigation ---
    def _get_next_sibling_index(self, current_idx):
        """Returns the index of the next object in the SAME image, or None."""
        if current_idx is None: return None

        col_name = "Fichier Original" if "Fichier Original" in self.df.columns else "Fichier"
        filename = self.df.at[current_idx, col_name]

        # Get all rows for this file
        siblings = self.df[self.df[col_name] == filename]

        # We need to find the "next" sibling.
        # Logic: Find current index in siblings list, return next one.
        # Ensure consistent sorting (e.g., by ID)
        if "ID" in siblings.columns:
            # Sort by ID to ensure logical next
            siblings = siblings.sort_values("ID")

        sibling_indices = siblings.index.tolist()

        if current_idx in sibling_indices:
            pos = sibling_indices.index(current_idx)
            if pos < len(sibling_indices) - 1:
                return sibling_indices[pos + 1]

        return None

    def on_sibling_select(self, event):
        selection = self.sibling_tree.selection()
        if not selection: return

        # Avoid recursion loop if selection was set programmatically
        # Check current active vs selected
        item = self.sibling_tree.item(selection[0])
        obj_id = item['values'][0]

        # Find index in DF
        rows = self.df[self.df['ID'] == obj_id].index.tolist()
        if rows:
            new_df_idx = rows[0]
            if new_df_idx == self.active_df_index:
                return # Already active

            self.active_df_index = new_df_idx

            # Sync Queue Index if possible
            if self.active_df_index in self.review_queue:
                self.current_queue_index = self.review_queue.index(self.active_df_index)
            else:
                # We are viewing an item NOT in the queue (detached)
                # Keep current_queue_index as is (it points to where we were)
                pass

            self.show_current_item(reload_siblings=False)

    def load_category_list(self):
        cats = {}
        try:
            csv_path = os.path.join(self.folder_path, "categories.csv")
            if not os.path.exists(csv_path):
                 if getattr(sys, 'frozen', False):
                     script_dir = os.path.dirname(sys.executable)
                 else:
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
            self.category_map = self.load_category_list()
            display_values = sorted(list(self.category_map.values()))
            entry = ttk.Combobox(row, values=display_values, font=("Arial", 10), state="readonly")
        elif name == "Etat":
            entry = ttk.Combobox(row, values=["Neuf", "Occasion", "Inconnu"], font=("Arial", 10))
        else:
            entry = tk.Entry(row, font=("Arial", 10))
        
        entry.pack(side="left", expand=True, fill="x")
        if readonly:
            entry.config(state="readonly")

        # Auto-save on focus out
        entry.bind("<FocusOut>", lambda e, n=name: self.on_field_focus_out(e, n))

        self.fields[name] = entry

    def on_field_focus_out(self, event, field_name):
        self.save_field_to_df(field_name)

    def save_field_to_df(self, field_name):
        if self.active_df_index is None: return

        # Don't auto-save readonly fields
        if field_name in ["ID", "Fichier", "Fichier Original", "Fiabilite"]: return

        try:
            val = self.fields[field_name].get()

            # Type conversion logic similar to validate_item
            if field_name == "Categorie":
                 # Convert Name back to ID if possible
                 for cid, cname in self.category_map.items():
                    if cname == val:
                        val = cid
                        break

            if field_name == "Quantite":
                 try: val = int(val)
                 except: pass
            elif field_name in ["Prix Unitaire", "Prix Neuf Estime"]:
                 try: val = float(val.replace(',', '.'))
                 except: pass

            self.df.at[self.active_df_index, field_name] = val

            # Recalculate Total Price
            try:
                q = float(self.df.at[self.active_df_index, "Quantite"])
                p = float(self.df.at[self.active_df_index, "Prix Unitaire"])
                self.df.at[self.active_df_index, "Prix Total"] = q * p
            except: pass

            self.save_data()

            # Update the sibling tree item specifically
            self._update_sibling_tree_item(self.active_df_index)

        except Exception as e:
            print(f"Auto-save error: {e}")

    def save_current_view(self):
        """Force save all fields in the current view to the DF."""
        if self.active_df_index is None: return
        for field in self.fields:
            self.save_field_to_df(field)

    def _update_sibling_tree_item(self, idx):
        # Helper to update just the current line in treeview without full rebuild
        try:
             curr_id = self.df.at[idx, "ID"]
             # Find item in tree
             for item in self.sibling_tree.get_children():
                 vals = self.sibling_tree.item(item, 'values')
                 if str(vals[0]) == str(curr_id):
                     new_vals = (
                        curr_id,
                        self.df.at[idx, "Nom"],
                        self.df.at[idx, "Quantite"],
                        self.df.at[idx, "Etat"],
                        self.df.at[idx, "Fiabilite"]
                     )
                     self.sibling_tree.item(item, values=new_vals)
                     break
        except: pass

    def _get_reliability_color(self, val):
        try: score = float(val)
        except: return "white"
        if score < 50: return "#ffcccc"
        elif score >= 90: return "#ccffcc"
        elif score < 70: return "#ffeeba"
        else: return "#fff3cd"

    def show_current_item(self, reload_siblings=True):
        if self.selection_rect_id:
            self.image_canvas.delete(self.selection_rect_id)
            self.selection_rect_id = None
            self.current_selection_coords = None

        self.current_rotation = 0
        file_col = "Fichier Original" if "Fichier Original" in self.df.columns else "Fichier"

        # Determine Active Index Logic
        if self.active_df_index is None:
            # Initialize from queue (which is now filenames)
            if self.current_queue_index < len(self.review_queue):
                current_filename = self.review_queue[self.current_queue_index]

                # Find all items for this file
                siblings = self.df[self.df[file_col] == current_filename]

                if not siblings.empty:
                    # Pick the one with the lowest reliability to show first
                    best_candidate = siblings.sort_values("Fiabilite", ascending=True).index[0]
                    self.active_df_index = best_candidate
                else:
                    # Should not happen if queue is consistent
                    messagebox.showerror("Erreur", f"Fichier dans la queue introuvable dans le CSV: {current_filename}")
                    self.current_queue_index += 1
                    self.show_current_item()
                    return
            else:
                 messagebox.showinfo("Terminé", "Aucun autre élément à réviser !")
                 self.root.quit()
                 return

        idx = self.active_df_index
        if idx not in self.df.index:
             self.active_df_index = None
             self.show_current_item()
             return

        row = self.df.loc[idx]
        current_filename = row.get(file_col, "")
        
        # Status Label Logic
        queue_pos = "?"
        if current_filename in self.review_queue:
            queue_pos = str(self.review_queue.index(current_filename) + 1)

        self.lbl_status.config(text=f"Objet ID: {row.get('ID', '?')} (Image: {queue_pos} / {len(self.review_queue)})")
        
        for field, entry in self.fields.items():
            val = row.get(field, "")
            if pd.isna(val): val = ""
            entry.config(state="normal")
            entry.delete(0, tk.END)
            if field == "Categorie":
                raw_val = str(val).strip()
                # Display Name if it's a known ID, otherwise keep existing value (Name or Custom)
                display_val = self.category_map.get(raw_val, raw_val)
                entry.set(display_val)
            else:
                entry.insert(0, str(val))
            if field in ["ID", "Fichier", "Fichier Original", "Fiabilite", "Categorie"]:
                entry.config(state="readonly")
            if field == "Fiabilite":
                color = self._get_reliability_color(val)
                entry.config(bg=color, readonlybackground=color)

        filename = row.get("Fichier Original", "")
        if not filename:
            filename = row.get("Fichier", "")
            
        if filename:
            if reload_siblings:
                self._update_sibling_list(filename, current_id=row.get('ID'))
            else:
                # Just highlight current
                self._highlight_sibling(row.get('ID'))

            image_path = os.path.join(self.processed_dir, str(filename))
            if not os.path.exists(image_path):
                image_path = os.path.join(self.folder_path, str(filename))
            
            if os.path.exists(image_path):
                self.current_image_path = image_path
                box_2d = None
                if "Box 2D" in row and pd.notna(row["Box 2D"]):
                    try:
                        val = row["Box 2D"]
                        if isinstance(val, str): box_2d = ast.literal_eval(val)
                        elif isinstance(val, list): box_2d = val
                    except: pass
                
                self.current_box_2d = box_2d
                self.display_image(image_path, box_2d)
            else:
                self.current_image_path = None
                self.display_placeholder(f"Image introuvable:\n{image_path}")
        else:
            self.current_image_path = None
            self.display_placeholder("Pas de nom de fichier dans le CSV")

    def _update_sibling_list(self, filename, current_id):
        for item in self.sibling_tree.get_children():
            self.sibling_tree.delete(item)
            
        if "Fichier Original" in self.df.columns:
            siblings = self.df[self.df["Fichier Original"] == filename]
        elif "Fichier" in self.df.columns:
             siblings = self.df[self.df["Fichier"] == filename]
        else: return

        for _, s_row in siblings.iterrows():
            values = (
                s_row.get("ID", ""),
                s_row.get("Nom", ""),
                s_row.get("Quantite", ""),
                s_row.get("Etat", ""),
                s_row.get("Fiabilite", "")
            )
            item_id = self.sibling_tree.insert("", "end", values=values)
            if str(s_row.get("ID")) == str(current_id):
                self.sibling_tree.selection_set(item_id)
                self.sibling_tree.see(item_id)
                self.sibling_tree.item(item_id, tags=("current",))

        self.sibling_tree.tag_configure("current", background="#d4edda")
        self.sibling_tree.tag_configure("hovered", background="#e2e6ea")

    def _highlight_sibling(self, current_id):
        # Update selection without rebuilding tree
        for item in self.sibling_tree.get_children():
            vals = self.sibling_tree.item(item, 'values')
            if str(vals[0]) == str(current_id):
                 self.sibling_tree.selection_set(item)
                 self.sibling_tree.see(item)
                 self.sibling_tree.item(item, tags=("current",))
            else:
                 self.sibling_tree.item(item, tags=())

    def display_image(self, path=None, box_2d=None):
        try:
            # If path provided, load and cache
            if path:
                self.original_image_object = Image.open(path)
                self.original_image_size = self.original_image_object.size

            img = self.original_image_object
            if not img: return

            # Calculate resize to fit canvas
            canvas_width = self.image_canvas.winfo_width()
            canvas_height = self.image_canvas.winfo_height()
            if canvas_width <= 1: canvas_width = 600
            if canvas_height <= 1: canvas_height = 600

            img_ratio = img.width / img.height
            canvas_ratio = canvas_width / canvas_height

            if img_ratio > canvas_ratio:
                new_width = canvas_width
                new_height = int(new_width / img_ratio)
            else:
                new_height = canvas_height
                new_width = int(new_height * img_ratio)

            if new_width < 1 or new_height < 1: return

            img_disp = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            self.tk_img = ImageTk.PhotoImage(img_disp)

            self.image_canvas.delete("all")
            x_center = canvas_width // 2
            y_center = canvas_height // 2
            self.image_canvas.create_image(x_center, y_center, image=self.tk_img, anchor="center")

            self.img_offset_x = x_center - (new_width // 2)
            self.img_offset_y = y_center - (new_height // 2)
            self.img_display_size = (new_width, new_height)
            self.box_map = {} # Reset map

            # Helper to draw box
            def draw_box(b2d, color, width, dash=None, item_id=None):
                if b2d and isinstance(b2d, list) and len(b2d) == 4:
                    try:
                        ymin, xmin, ymax, xmax = b2d
                        left = (xmin / 1000) * new_width + self.img_offset_x
                        top = (ymin / 1000) * new_height + self.img_offset_y
                        right = (xmax / 1000) * new_width + self.img_offset_x
                        bottom = (ymax / 1000) * new_height + self.img_offset_y
                        rect_id = self.image_canvas.create_rectangle(left, top, right, bottom, outline=color, width=width, dash=dash)
                        if item_id is not None:
                            self.box_map[rect_id] = item_id
                            # Bind hover events to this rectangle
                            self.image_canvas.tag_bind(rect_id, "<Enter>", lambda e, i=item_id: self.on_box_enter(i))
                            self.image_canvas.tag_bind(rect_id, "<Leave>", self.on_box_leave)
                        return rect_id
                    except Exception: pass
                return None

            # 1. Draw all other siblings if enabled
            if self.show_all_boxes_var.get() and self.current_image_path:
                # Resolve filename reliably from DF if possible
                filename = None
                col_name = "Fichier Original" if "Fichier Original" in self.df.columns else "Fichier"

                if self.active_df_index is not None:
                     try:
                         filename = self.df.at[self.active_df_index, col_name]
                     except: pass

                if not filename:
                    filename = os.path.basename(self.current_image_path)

                siblings = self.df[self.df[col_name] == filename]

                current_id = self.df.at[self.active_df_index, "ID"] if self.active_df_index is not None else None

                for idx, row in siblings.iterrows():
                    # Skip current item, draw it last/special
                    # Use string comparison to be safe against int/str type mismatches
                    if str(row.get("ID")) == str(current_id): continue

                    s_box = None
                    if "Box 2D" in row and pd.notna(row["Box 2D"]):
                         try:
                            val = row["Box 2D"]
                            if isinstance(val, str): s_box = ast.literal_eval(val)
                            elif isinstance(val, list): s_box = val
                         except: pass

                    if s_box:
                        draw_box(s_box, "blue", 1, None, row.get("ID"))

            # 2. Draw current item box
            if box_2d:
                current_id = self.df.at[self.active_df_index, "ID"] if self.active_df_index is not None else None
                draw_box(box_2d, "#00ff00", 3, (5, 5), current_id)
            
        except Exception as e:
            self.display_placeholder(f"Erreur image: {e}")

    def rotate_image(self, direction="left"):
        if self.current_image_path and os.path.exists(self.current_image_path):
            try:
                # Rotate the physical image (PIL rotates CCW by default)
                # left = 90 deg CCW
                # right = -90 deg CCW
                angle = 90 if direction == "left" else -90
                img = Image.open(self.current_image_path)
                img = img.rotate(angle, expand=True)
                img.save(self.current_image_path)

                # Rotate Bounding Boxes for ALL items on this image
                file_col = "Fichier Original" if "Fichier Original" in self.df.columns else "Fichier"
                filename = os.path.basename(self.current_image_path)

                siblings = self.df[self.df[file_col] == filename]

                for idx in siblings.index:
                    if pd.notna(self.df.at[idx, "Box 2D"]):
                        try:
                            val = self.df.at[idx, "Box 2D"]
                            if isinstance(val, str): b2d = ast.literal_eval(val)
                            elif isinstance(val, list): b2d = val
                            else: continue

                            if len(b2d) == 4:
                                ymin, xmin, ymax, xmax = b2d
                                # Coordinate Transform in normalized (0-1000) space
                                
                                if direction == "left":
                                    # 90 deg CCW
                                    # x' = y
                                    # y' = 1000 - x
                                    new_ymin = 1000 - xmax
                                    new_xmin = ymin
                                    new_ymax = 1000 - xmin
                                    new_xmax = ymax
                                else:
                                    # 90 deg CW (Right)
                                    # x' = 1000 - y
                                    # y' = x
                                    new_ymin = xmin
                                    new_xmin = 1000 - ymax
                                    new_ymax = xmax
                                    new_xmax = 1000 - ymin

                                # Ensure min/max order
                                final_ymin = min(new_ymin, new_ymax)
                                final_ymax = max(new_ymin, new_ymax)
                                final_xmin = min(new_xmin, new_xmax)
                                final_xmax = max(new_xmin, new_xmax)

                                self.df.at[idx, "Box 2D"] = str([final_ymin, final_xmin, final_ymax, final_xmax])
                        except Exception as e:
                            print(f"Failed to rotate box for idx {idx}: {e}")

                # Update current view variables
                if self.active_df_index is not None:
                    raw_box = self.df.at[self.active_df_index, "Box 2D"]
                    if isinstance(raw_box, str):
                        try: self.current_box_2d = ast.literal_eval(raw_box)
                        except: self.current_box_2d = None
                    else:
                        self.current_box_2d = raw_box

                self.save_data()
                self.display_image(self.current_image_path, self.current_box_2d)
            except Exception as e:
                messagebox.showerror("Erreur", f"Impossible de pivoter l'image: {e}")

    def display_placeholder(self, text):
        self.image_canvas.delete("all")
        self.image_canvas.create_text(200, 200, text=text, fill="white")

    def comment_and_skip_item(self):
        idx = self.active_df_index
        if idx is not None:
            try:
                self.df.at[idx, "Commentaire"] = self.get_field_value("Commentaire")
                self.save_data()
                self.next_item()
            except Exception as e:
                messagebox.showerror("Erreur", f"Erreur lors du commentaire: {e}")

    def get_field_value(self, name):
        return self.fields[name].get()

    def validate_item(self):
        idx = self.active_df_index
        if idx is None: return
        try:
            self.df.at[idx, "Nom"] = self.get_field_value("Nom")
            cat_name = self.get_field_value("Categorie")
            # Convert Name -> ID if possible, else preserve value
            cat_id = cat_name
            for cid, cname in self.category_map.items():
                if cname == cat_name:
                    cat_id = cid
                    break
            self.df.at[idx, "Categorie"] = cat_id
            self.df.at[idx, "Etat"] = self.get_field_value("Etat")
            self.df.at[idx, "Commentaire"] = self.get_field_value("Commentaire")
            
            try: self.df.at[idx, "Quantite"] = int(self.get_field_value("Quantite"))
            except: pass
            
            try: self.df.at[idx, "Prix Unitaire"] = float(str(self.get_field_value("Prix Unitaire")).replace(',', '.'))
            except: pass
            
            try: self.df.at[idx, "Prix Neuf Estime"] = float(str(self.get_field_value("Prix Neuf Estime")).replace(',', '.'))
            except: pass
            
            try:
                q = float(self.df.at[idx, "Quantite"])
                p = float(self.df.at[idx, "Prix Unitaire"])
                self.df.at[idx, "Prix Total"] = q * p
            except: pass
            
            self.df.at[idx, "Fiabilite"] = 100
            
            self.save_data()

            # Navigate to next object (Sibling -> Next Image)
            next_sibling_idx = self._get_next_sibling_index(idx)

            if next_sibling_idx is not None:
                self.active_df_index = next_sibling_idx
                # Update queue index if applicable
                if self.active_df_index in self.review_queue:
                    self.current_queue_index = self.review_queue.index(self.active_df_index)
                self.show_current_item(reload_siblings=False)
            else:
                self.next_item()
            
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de la validation: {e}")

    def delete_item(self):
        idx = self.active_df_index
        if idx is None: return

        # Check for siblings
        col_name = "Fichier Original" if "Fichier Original" in self.df.columns else "Fichier"
        filename = self.df.at[idx, col_name]
        siblings = self.df[self.df[col_name] == filename]

        is_last = len(siblings) <= 1

        msg = "Voulez-vous vraiment supprimer cette ligne de l'inventaire ?"
        if is_last:
            msg = "ATTENTION : C'est le dernier objet de cette image.\nSi vous le supprimez, l'image sera considérée comme vide/traitée.\n\nVoulez-vous supprimer ?"

        should_delete = True
        if is_last:
             should_delete = messagebox.askyesno("Confirmer", msg)

        if should_delete:
            try:
                self.df = self.df.drop(idx)

                # Check if file still has siblings
                remaining = self.df[self.df[col_name] == filename]

                if remaining.empty:
                    # Remove filename from queue if no items left
                    if filename in self.review_queue:
                        self.review_queue.remove(filename)
                
                self.save_data()

                # Logic for what to show next
                if is_last:
                    # No siblings left, go to next image (queue logic)
                    self.active_df_index = None
                    # Fix queue index if it shifted (queue length reduced)
                    if self.current_queue_index >= len(self.review_queue):
                        self.current_queue_index = max(0, len(self.review_queue) - 1)
                    self.show_current_item()
                else:
                    # Siblings exist, switch to one of them
                    if not remaining.empty:
                        self.active_df_index = remaining.index[0]
                        self.show_current_item(reload_siblings=True)
                    else:
                        self.active_df_index = None
                        self.show_current_item()

            except Exception as e:
                messagebox.showerror("Erreur", f"Erreur lors de la suppression: {e}")

    def prev_item(self):
        self.save_current_view()
        # Move backward to the PREVIOUS IMAGE in queue
        if self.current_queue_index > 0:
            self.current_queue_index -= 1
        else:
            # Loop to last
            self.current_queue_index = len(self.review_queue) - 1
            
        self.active_df_index = None
        self.show_current_item()

    def rescan_item(self):
        if not self.current_image_path:
            messagebox.showwarning("Attention", "Pas d'image chargée pour l'analyse.")
            return

        has_selection = self.current_selection_coords is not None
        msg = "Rescan CIBLÉ sur la zone rouge sélectionnée.\nEntrez un indice (optionnel):" if has_selection else "Rescan de TOUTE l'image.\nEntrez un indice (optionnel):"

        hint = simpledialog.askstring("Rescan IA", msg)
        if hint is None: return
            
        try:
            self.root.config(cursor="watch")
            self.update_status("Démarrage du rescan...")
            
            target_image_path = self.current_image_path
            temp_crop_path = None
            crop_info = None

            if has_selection:
                x1, y1, x2, y2 = self.current_selection_coords
                img_x1 = x1 - self.img_offset_x
                img_y1 = y1 - self.img_offset_y
                img_x2 = x2 - self.img_offset_x
                img_y2 = y2 - self.img_offset_y

                disp_w, disp_h = self.img_display_size
                orig_w, orig_h = self.original_image_size

                scale_x = orig_w / disp_w
                scale_y = orig_h / disp_h

                final_x1 = max(0, int(img_x1 * scale_x))
                final_y1 = max(0, int(img_y1 * scale_y))
                final_x2 = min(orig_w, int(img_x2 * scale_x))
                final_y2 = min(orig_h, int(img_y2 * scale_y))

                if (final_x2 - final_x1) > 10 and (final_y2 - final_y1) > 10:
                    try:
                        img = Image.open(self.current_image_path)
                        crop = img.crop((final_x1, final_y1, final_x2, final_y2))
                        temp_crop_path = os.path.join(self.folder_path, "temp_rescan_crop.jpg")
                        crop.save(temp_crop_path)
                        target_image_path = temp_crop_path
                        crop_info = (final_x1, final_y1, final_x2 - final_x1, final_y2 - final_y1)
                    except Exception as e:
                        print(f"Crop failed: {e}")
                        target_image_path = self.current_image_path

            result = analyze_image(target_image_path, categories_context=self.categories_context, user_hint=hint, status_callback=self.update_status)
            
            if crop_info and result.get("box_2d") and isinstance(result["box_2d"], list) and len(result["box_2d"]) == 4:
                local_box = result["box_2d"]
                crop_x, crop_y, crop_w, crop_h = crop_info
                orig_w, orig_h = self.original_image_size

                l_ymin = (local_box[0] / 1000.0) * crop_h
                l_xmin = (local_box[1] / 1000.0) * crop_w
                l_ymax = (local_box[2] / 1000.0) * crop_h
                l_xmax = (local_box[3] / 1000.0) * crop_w

                f_ymin = int(((l_ymin + crop_y) / orig_h) * 1000)
                f_xmin = int(((l_xmin + crop_x) / orig_w) * 1000)
                f_ymax = int(((l_ymax + crop_y) / orig_h) * 1000)
                f_xmax = int(((l_xmax + crop_x) / orig_w) * 1000)

                result["box_2d"] = [f_ymin, f_xmin, f_ymax, f_xmax]

            self._apply_scan_result(result)
            # Ensure siblings list is updated because reliability or other data might have changed
            self.show_current_item(reload_siblings=True)

            if temp_crop_path and os.path.exists(temp_crop_path):
                try: os.remove(temp_crop_path)
                except: pass

            self.update_status("Analyse terminée.")
            messagebox.showinfo("Succès", "Analyse terminée ! Vérifiez les valeurs avant de valider.")
            
        except Exception as e:
            self.update_status(f"Erreur: {e}")
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
            self.update_status("Démarrage du scan multi-objets...")
            
            results = analyze_image_multiple(self.current_image_path, categories_context=self.categories_context, user_hint=hint, target_element=hint, status_callback=self.update_status)
            if not isinstance(results, list): results = [results]
            if len(results) == 0:
                self.update_status("Aucun objet détecté.")
                messagebox.showinfo("Résultat", "Aucun objet détecté.")
                return
                
            first_item = results[0]
            self._apply_scan_result(first_item)
            
            new_rows_count = 0
            if len(results) > 1:
                idx = self.active_df_index
                current_row_data = self.df.loc[idx].to_dict()
                
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
                    
                    mapping = {
                        "nom": "Nom", "categorie": "Categorie", "etat": "Etat",
                        "quantite": "Quantite", "prix_unitaire_estime": "Prix Unitaire",
                        "prix_neuf_estime": "Prix Neuf Estime"
                    }
                    for res_key, df_key in mapping.items():
                        val = item.get(res_key, "")
                        if df_key in ["Quantite", "Prix Unitaire", "Prix Neuf Estime", "Prix Total"]:
                             try: val = float(str(val))
                             except: pass
                        new_row[df_key] = val
                        
                    try:
                        q = float(new_row.get("Quantite", 0))
                        p = float(new_row.get("Prix Unitaire", 0))
                        new_row["Prix Total"] = q * p
                    except: pass
                    
                    if "box_2d" in item and item["box_2d"]:
                        new_row["Box 2D"] = str(item["box_2d"])

                    self.df = pd.concat([self.df, pd.DataFrame([new_row])], ignore_index=True)

                self.save_data()
                self._update_sibling_list(current_row_data.get("Fichier Original"), current_row_data.get("ID"))

            self.show_current_item(reload_siblings=True)
            messagebox.showinfo("Succès", f"Analyse terminée !\n\nObjet courant mis à jour.\n{new_rows_count} nouveaux objets ajoutés à la suite.")

        except Exception as e:
            messagebox.showerror("Erreur", f"Echec du scan multi: {e}")
        finally:
            self.root.config(cursor="")

    def _apply_scan_result(self, result):
        fields_map = {
            "Nom": "nom", "Categorie": "categorie", "Etat": "etat",
            "Quantite": "quantite", "Prix Unitaire": "prix_unitaire_estime",
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
                    if isinstance(entry, ttk.Combobox):
                        entry.set(str(val))
                    else:
                        entry.delete(0, tk.END)
                        entry.insert(0, str(val))

                    if ui_field == "Categorie":
                        entry.config(state="readonly")
                
        if "box_2d" in result and result["box_2d"]:
            idx = self.active_df_index
            self.df.at[idx, "Box 2D"] = str(result["box_2d"])
            self.current_box_2d = result["box_2d"]
            self.display_image(None, self.current_box_2d)

        try:
            idx = self.active_df_index
            for ui_field, result_key in fields_map.items():
                if result_key in result:
                    val = result[result_key]
                    if ui_field == "Categorie":
                        if "categorie_id" in result: val = result["categorie_id"]
                    if ui_field in ["Quantite"]:
                         try: val = int(float(str(val)))
                         except: pass
                    elif ui_field in ["Prix Unitaire", "Prix Neuf Estime"]:
                         try: val = float(str(val))
                         except: pass
                    self.df.at[idx, ui_field] = val
            
            try:
                q = float(self.df.at[idx, "Quantite"])
                p = float(self.df.at[idx, "Prix Unitaire"])
                self.df.at[idx, "Prix Total"] = q * p
            except: pass
            
            if "fiabilite" in result:
                 self.df.at[idx, "Fiabilite"] = result["fiabilite"]
                 if "Fiabilite" in self.fields:
                      fval = result["fiabilite"]
                      entry = self.fields["Fiabilite"]
                      entry.config(state="normal")
                      entry.delete(0, tk.END)
                      entry.insert(0, str(fval))
                      entry.config(state="readonly")
                      color = self._get_reliability_color(fval)
                      entry.config(bg=color, readonlybackground=color)

            self.save_data()
            self._update_sibling_list(self.df.at[idx, "Fichier Original"], self.df.at[idx, "ID"])
            
        except Exception as e:
            print(f"Error saving rescan result immediately: {e}")

    def mark_as_retake(self):
        if self.current_queue_index >= len(self.review_queue): return
        # Logic here works on Active Index if we are consistent, but typically retake is for bad images.
        current_idx = self.active_df_index
        
        if not self.current_image_path or not os.path.exists(self.current_image_path):
             messagebox.showwarning("Attention", "Pas d'image trouvée à déplacer.")
        
        try:
            filename = None
            if self.current_image_path:
                 filename = os.path.basename(self.current_image_path)
            
            sharing_indices = []
            if filename:
                 if "Fichier Original" in self.df.columns:
                     sharing_indices = self.df[self.df["Fichier Original"] == filename].index.tolist()
                 elif "Fichier" in self.df.columns:
                     sharing_indices = self.df[self.df["Fichier"] == filename].index.tolist()

            is_multi_object = len(sharing_indices) > 1
            indices_to_drop = [current_idx]
            keep_original_file = is_multi_object
            
            if not is_multi_object:
                if sharing_indices: indices_to_drop = sharing_indices
            
            if self.current_image_path and os.path.exists(self.current_image_path):
                 retake_dir = os.path.join(self.folder_path, RETAKE_FOLDER_NAME)
                 if not os.path.exists(retake_dir): os.makedirs(retake_dir)
                 
                 dest_path = os.path.join(retake_dir, filename)
                 if os.path.exists(dest_path):
                      base, ext = os.path.splitext(filename)
                      import time
                      dest_path = os.path.join(retake_dir, f"{base}_{int(time.time())}{ext}")
                 
                 img = Image.open(self.current_image_path)
                 if hasattr(self, 'current_box_2d') and self.current_box_2d:
                     try:
                         draw = ImageDraw.Draw(img)
                         ymin, xmin, ymax, xmax = self.current_box_2d
                         width, height = img.size
                         left = (xmin / 1000) * width
                         top = (ymin / 1000) * height
                         right = (xmax / 1000) * width
                         bottom = (ymax / 1000) * height
                         draw.rectangle([left, top, right, bottom], outline="red", width=5)
                     except Exception: pass

                 img.save(dest_path)
                 
                 if not keep_original_file:
                     try:
                        img.close()
                        os.remove(self.current_image_path)
                        self.current_image_path = None
                     except Exception: pass

            col_name = "Fichier Original" if "Fichier Original" in self.df.columns else "Fichier"
            if indices_to_drop:
                self.df = self.df.drop(indices_to_drop)
                
                # Update queue - remove filename if no items left
                remaining = self.df[self.df[col_name] == filename]
                if remaining.empty and filename in self.review_queue:
                    self.review_queue.remove(filename)

                self.active_df_index = None # Reset

                if self.current_queue_index >= len(self.review_queue):
                    self.current_queue_index = len(self.review_queue) - 1
                if self.current_queue_index < 0:
                    self.current_queue_index = 0

            self.save_data()
            self.show_current_item()
            
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors du marquage à refaire: {e}")

    def next_item(self):
        self.save_current_view()
        # Move forward to the NEXT IMAGE in queue
        if self.current_queue_index < len(self.review_queue) - 1:
            self.current_queue_index += 1
        else:
            # Loop to first
            self.current_queue_index = 0
            
        self.active_df_index = None
        self.show_current_item()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Review inventory items.")
    parser.add_argument("csv_file", help="Path to the inventory CSV file")
    args = parser.parse_args()
    
    root = tk.Tk()
    app = ReviewApp(root, args.csv_file)
    root.mainloop()
