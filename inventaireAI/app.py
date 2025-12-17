import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import os
import sys

# Import our functional modules
# Ensure we can import even if bundled with PyInstaller
if getattr(sys, 'frozen', False):
    os.chdir(sys._MEIPASS)

from counter import process_inventory
from review_gui import ReviewApp
from ui_utils import ToolTip
from settings_gui import SettingsDialog

from version_info import VERSION, BUILD_DATE
from update_checker import check_for_updates_thread

class LauncherApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Inventaire AI - Launcher v{VERSION}")
        self.root.geometry("750x650") # Larger window for better layout
        self.root.minsize(600, 600)
        self.root.configure(bg="#f8f9fa")
        
        # Check updates
        check_for_updates_thread(self.on_update_result)
        
        # Style
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("Big.TButton", font=("Segoe UI", 12, "bold"), padding=10)
        self.style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), background="#f8f9fa", foreground="#2c3e50")
        self.style.configure("Header.TLabel", font=("Segoe UI", 12, "bold"), background="#f8f9fa", foreground="#34495e")
        self.style.configure("Step.TLabel", font=("Segoe UI", 11, "bold"), background="#ffffff", foreground="#2980b9")
        self.style.configure("Normal.TLabel", font=("Segoe UI", 10), background="#ffffff", foreground="#555")

        # Main Container
        main_frame = tk.Frame(root, bg="#f8f9fa")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Update Notification Area (Top)
        self.lbl_ver = tk.Label(main_frame, text=f"v{VERSION} - Régie des Quartiers", bg="#f8f9fa", fg="#bdc3c7", font=("Segoe UI", 9))
        self.lbl_ver.pack(side="bottom", pady=(10, 0))

        # Title
        lbl_title = ttk.Label(main_frame, text="Inventaire AI - Assistant", style="Title.TLabel")
        lbl_title.pack(pady=(0, 20))

        # --- INSTRUCTIONS PANEL ---
        instr_frame = tk.LabelFrame(main_frame, text="  Guide d'Utilisation  ", font=("Segoe UI", 11, "bold"), bg="#ffffff", fg="#333", padx=15, pady=15, relief="flat", bd=1)
        instr_frame.pack(fill="x", pady=(0, 20))
        
        # Steps
        steps = [
            ("1. SCAN", "Cliquez sur 'Nouvel Inventaire'. Sélectionnez votre dossier.\n L'IA identifie les objets (plusieurs par photo possibles si bien visibles).\n Si vous ajoutez des photos, relancez simplement le scan : seules les nouvelles seront ajoutées."),
            ("2. VERIFICATION", "Ouvrez le fichier CSV généré avec 'Réviser / Corriger'.\n Les résultats sont triés par 'Fiabilité' croissante : l'IA vous montre en premier\n les éléments les plus difficiles à identifier pour faciliter votre contrôle."),
            ("3. CORRECTION", "Si une photo est mal cadrée, floue ou contient plusieurs objets :\nUtilisez le bouton 'À Refaire'. L'image sera déplacée dans le dossier 'a_refaire'\npour que vous puissiez la reprendre proprement.")
        ]
        
        for title, desc in steps:
            step_container = tk.Frame(instr_frame, bg="#ffffff", pady=5)
            step_container.pack(fill="x", anchor="w")
            ttk.Label(step_container, text=title, style="Step.TLabel").pack(anchor="w")
            tk.Label(step_container, text=desc, bg="#ffffff", fg="#555", font=("Segoe UI", 10), justify="left").pack(anchor="w", padx=(0, 0))

        # --- DISCLAIMER PANEL ---
        disclaimer_frame = tk.Frame(main_frame, bg="#fef9e7", padx=10, pady=10, relief="solid", bd=1) # Light yellow warning bg
        disclaimer_frame.pack(fill="x", pady=(0, 25))
        
        disc_icon = tk.Label(disclaimer_frame, text="⚠️", bg="#fef9e7", font=("Segoe UI", 14))
        disc_icon.pack(side="left", padx=(5, 10))
        
        disclaimer_text = (
            "COUT & LIMITES : Environ 0,001 € par photo (1€ / 1000 photos).\n"
            "Outil conçu pour des volumes modérés. Ne pas lancer sur des banques d'images massives."
        )
        tk.Label(disclaimer_frame, text=disclaimer_text, bg="#fef9e7", fg="#7f8c8d", font=("Segoe UI", 9, "bold"), justify="left").pack(side="left")

        # --- ACTIONS PANEL ---
        btn_frame = tk.Frame(main_frame, bg="#f8f9fa")
        btn_frame.pack(fill="x", expand=True)
        
        # Grid layout for buttons for better centering
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)
        btn_frame.columnconfigure(2, weight=1) # Added for settings button if we want 3 columns, or keep 2 and put settings below

        self.btn_scan = ttk.Button(
            btn_frame, 
            text="🆕  NOUVEL INVENTAIRE\nScanner un dossier", 
            style="Big.TButton", 
            command=self.start_new_inventory
        )
        self.btn_scan.grid(row=0, column=0, padx=5, sticky="ew")
        
        self.btn_review = ttk.Button(
            btn_frame, 
            text="🛠️  REVISER / CORRIGER\nOuvrir un inventaire", 
            style="Big.TButton", 
            command=self.start_review
        )
        self.btn_review.grid(row=0, column=1, padx=5, sticky="ew")

        # Settings Button (Row 1 or Column 2?)
        # Let's put it in a separate row or smaller button

        self.btn_settings = ttk.Button(
            main_frame,
            text="⚙️  Paramètres & Configuration",
            command=self.open_settings
        )
        self.btn_settings.pack(pady=(15, 0), anchor="e") # Bottom right of main frame actions

    def open_settings(self):
        SettingsDialog(self.root)

    def on_update_result(self, result):
        has_update, new_ver, error = result
        if has_update:
            self.root.after(0, lambda: self.show_update_notification(new_ver))
            
    def show_update_notification(self, new_ver):
        msg = f"Une nouvelle version (v{new_ver}) est disponible !\nVeuillez mettre à jour l'application."
        self.lbl_ver.config(text=msg, fg="red", font=("Arial", 10, "bold"))
        messagebox.showinfo("Mise à jour disponible", msg)


    def start_new_inventory(self):
        folder_selected = filedialog.askdirectory(title="Sélectionner le dossier contenant les photos")
        if not folder_selected:
            return

        # Create Progress Popup
        self.popup = tk.Toplevel(self.root)
        self.popup.title("Analyse en cours...")
        self.popup.geometry("400x150")
        self.popup.transient(self.root)
        self.popup.grab_set()
        
        self.stop_event = threading.Event()
        self.popup.protocol("WM_DELETE_WINDOW", self.on_cancel_scan)
        
        lbl = tk.Label(self.popup, text="Analyse des images par l'IA...\nVeuillez patienter.", pady=10, font=("Arial", 11))
        lbl.pack()
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self.popup, orient="horizontal", length=300, mode="determinate", variable=self.progress_var)
        self.progress_bar.pack(pady=10)
        
        self.lbl_status = tk.Label(self.popup, text="Préparation...", fg="gray")
        self.lbl_status.pack()

        # Run in thread
        threading.Thread(target=self.run_process_inventory, args=(folder_selected,), daemon=True).start()

    def on_cancel_scan(self):
        if messagebox.askyesno("Annuler", "Voulez-vous vraiment arrêter le scan en cours ?"):
            self.stop_event.set()
            self.popup.destroy()

    def run_process_inventory(self, folder_path):
        try:
            csv_path = process_inventory(folder_path, progress_callback=self.update_progress, stop_event=self.stop_event)
            
            if not self.stop_event.is_set():
                self.root.after(0, lambda: self.finish_inventory(csv_path))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Erreur", f"Une erreur est survenue:\n{e}"))
            self.root.after(0, self.popup.destroy)

    def update_progress(self, current, total, message):
        progress = (current / total) * 100
        self.root.after(0, lambda: self.progress_var.set(progress))
        self.root.after(0, lambda: self.lbl_status.config(text=message))

    def finish_inventory(self, csv_path):
        self.popup.destroy()
        if csv_path and os.path.exists(csv_path):
            if messagebox.askyesno("Succès", f"Inventaire terminé !\nFichier créé : {os.path.basename(csv_path)}\n\nVoulez-vous lancer la révision maintenant ?"):
                self.launch_review_interface(csv_path)
        else:
            messagebox.showwarning("Attention", "Aucun fichier CSV n'a été généré (peut-être aucune image trouvée ?).")

    def start_review(self):
        csv_file = filedialog.askopenfilename(title="Ouvrir un fichier inventaire CSV", filetypes=[("CSV Files", "*.csv")])
        if not csv_file:
            return
        
        self.launch_review_interface(csv_file)

    def launch_review_interface(self, csv_path):
        # We need to hide launcher or open new window
        # ReviewApp uses 'root', so we can pass a Toplevel
        
        review_window = tk.Toplevel(self.root)
        # Handle close of review window
        def on_close():
            review_window.destroy()
            self.root.deiconify() # Bring back launcher
            
        review_window.protocol("WM_DELETE_WINDOW", on_close)
        
        # Initialize Review App in this window
        try:
            app = ReviewApp(review_window, csv_path)
            # Hide launcher while reviewing
            self.root.withdraw()
        except Exception as e:
             messagebox.showerror("Erreur", f"Impossible d'ouvrir la révision : {e}")
             review_window.destroy()
             self.root.deiconify()

if __name__ == "__main__":
    root = tk.Tk()
    app = LauncherApp(root)
    root.mainloop()
