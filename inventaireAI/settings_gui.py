import tkinter as tk
from tkinter import ttk, messagebox
import os
from dotenv import load_dotenv, set_key

class SettingsDialog:
    def __init__(self, parent):
        self.top = tk.Toplevel(parent)
        self.top.title("Paramètres / Configuration")
        self.top.geometry("600x450")
        self.top.transient(parent)
        self.top.grab_set()

        # Load current env vars explicitly
        self.env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        load_dotenv(self.env_path)

        self.style = ttk.Style()
        self.style.configure("Bold.TLabel", font=("Segoe UI", 10, "bold"))

        self.create_widgets()

    def create_widgets(self):
        container = ttk.Frame(self.top, padding=20)
        container.pack(fill="both", expand=True)

        # Title
        ttk.Label(container, text="Configuration Globale", font=("Segoe UI", 14, "bold")).pack(pady=(0, 20))

        # Form Grid
        form_frame = ttk.Frame(container)
        form_frame.pack(fill="x", expand=True)
        form_frame.columnconfigure(1, weight=1)

        row = 0

        # API KEY
        self.create_row(form_frame, row, "Clé API Google (Gemini):", "GOOGLE_API_KEY", secret=True)
        row += 1

        # Reliability Threshold
        self.create_row(form_frame, row, "Seuil de Fiabilité (0-100):", "RELIABILITY_THRESHOLD",
                       desc="En dessous de ce score, l'IA demandera confirmation ou déplacera l'image.")
        row += 1

        # Compression Size
        self.create_row(form_frame, row, "Taille Max Compression (Ko):", "COMPRESSION_MAX_SIZE_KB",
                       desc="Taille cible pour les images sauvegardées (ex: 250).")
        row += 1

        # Additional CSV Columns
        self.create_row(form_frame, row, "Colonnes CSV Supplémentaires:", "ADDITIONAL_CSV_COLUMNS",
                       desc="Séparées par virgule (ex: Emplacement,Remarques).")
        row += 1

        # Buttons
        btn_frame = ttk.Frame(container)
        btn_frame.pack(fill="x", pady=30)

        ttk.Button(btn_frame, text="Annuler", command=self.top.destroy).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="💾 Sauvegarder", command=self.save_settings).pack(side="right", padx=5)

    def create_row(self, parent, row, label_text, env_key, secret=False, desc=None):
        ttk.Label(parent, text=label_text, style="Bold.TLabel").grid(row=row*2, column=0, sticky="w", pady=(10, 2))

        entry = ttk.Entry(parent, show="*" if secret else "")
        val = os.getenv(env_key, "")
        entry.insert(0, val)
        entry.grid(row=row*2, column=1, sticky="ew", padx=(10, 0), pady=(10, 2))

        if desc:
            ttk.Label(parent, text=desc, font=("Segoe UI", 8), foreground="#666").grid(row=row*2+1, column=1, sticky="w", padx=(10, 0))

        # Store reference
        if not hasattr(self, 'entries'): self.entries = {}
        self.entries[env_key] = entry

    def save_settings(self):
        try:
            # Create .env if not exists
            if not os.path.exists(self.env_path):
                with open(self.env_path, 'w') as f: f.write("")

            changes_count = 0
            for key, entry in self.entries.items():
                new_val = entry.get().strip()
                # Basic validation
                if key == "RELIABILITY_THRESHOLD":
                    if not new_val.isdigit() or not (0 <= int(new_val) <= 100):
                        messagebox.showerror("Erreur", "Le seuil de fiabilité doit être entre 0 et 100.")
                        return

                # Update .env file using dotenv.set_key to preserve format if possible,
                # but set_key writes to file immediately.
                current_val = os.getenv(key)
                if new_val != current_val:
                    set_key(self.env_path, key, new_val)
                    os.environ[key] = new_val # Update current session too
                    changes_count += 1

            if changes_count > 0:
                messagebox.showinfo("Succès", "Paramètres sauvegardés avec succès !")
            else:
                messagebox.showinfo("Info", "Aucun changement détecté.")

            self.top.destroy()

        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de sauvegarder : {e}")
