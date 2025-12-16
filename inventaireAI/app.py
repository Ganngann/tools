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

from version_info import VERSION, BUILD_DATE
from update_checker import check_for_updates_thread

class LauncherApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Inventaire AI - Launcher v{VERSION}")
        self.root.geometry("600x550")
        self.root.minsize(450, 500)
        self.root.configure(bg="#f0f2f5")
        
        # Check updates
        check_for_updates_thread(self.on_update_result)
        
        # Style
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("Big.TButton", font=("Arial", 14), padding=15)
        self.style.configure("Title.TLabel", font=("Arial", 24, "bold"), background="#f0f2f5", foreground="#333")
        self.style.configure("Sub.TLabel", font=("Arial", 12), background="#f0f2f5", foreground="#666")

        # Header
        header_frame = tk.Frame(root, bg="#f0f2f5", pady=20)
        header_frame.pack(fill="x", padx=20)
        
        lbl_title = ttk.Label(header_frame, text="Inventaire AI", style="Title.TLabel")
        lbl_title.pack()
        
        lbl_sub = ttk.Label(header_frame, text="Choisissez une action pour commencer", style="Sub.TLabel")
        lbl_sub.pack(pady=(5, 10))

        # Explanations
        expl_text = (
            "1. 🆕 Lancez un scan sur un dossier de photos.\n"
            "   -> L'IA compte les objets et crée un fichier CSV.\n\n"
            "2. 🛠️ Ouvrez ce CSV pour valider les résultats.\n"
            "   -> Corrigez les erreurs, ajoutez les prix.\n"
            "   -> Bouton 'À Refaire' : déplace la photo dans le dossier 'a_refaire'\n"
            "      pour que vous puissiez la reprendre plus tard."
        )
        lbl_expl = tk.Label(
            header_frame, 
            text=expl_text, 
            bg="#e1e4e8", 
            fg="#333", 
            justify="left", 
            font=("Arial", 11),
            padx=15, 
            pady=15,
            wraplength=550,
            relief="groove",
            borderwidth=1
        )
        lbl_expl.pack(fill="x", pady=(0, 10), padx=10)

        # Cost Disclaimer
        disclaimer_text = (
            "ℹ️ Note : Le coût est d'environ 0,001 € par photo (soit 1 € pour 1000 photos).\n"
            "   L'outil est libre d'utilisation, mais n'est pas conçu pour traiter\n"
            "   des volumes massifs (ex: 1 million de photos)."
        )
        lbl_disclaimer = tk.Label(
            header_frame,
            text=disclaimer_text,
            bg="#f0f2f5",
            fg="#666",
            justify="center",
            font=("Arial", 9, "italic")
        )
        lbl_disclaimer.pack(fill="x", pady=(0, 10))

        # Buttons Frame
        btn_frame = tk.Frame(root, bg="#f0f2f5", pady=10)
        btn_frame.pack(expand=True, fill="x", padx=40)

        self.btn_scan = ttk.Button(
            btn_frame, 
            text="🆕 Nouvel Inventaire\n(Scanner des photos)", 
            style="Big.TButton", 
            command=self.start_new_inventory
        )
        self.btn_scan.pack(fill="x", pady=10)
        ToolTip(self.btn_scan, "Sélectionnez un dossier de photos.\nL'IA analysera chaque image pour créer un fichier Excel (CSV).")

        self.btn_review = ttk.Button(
            btn_frame, 
            text="🛠️ Réviser / Corriger\n(Ouvrir un CSV)", 
            style="Big.TButton", 
            command=self.start_review
        )
        self.btn_review.pack(fill="x", pady=10)
        ToolTip(self.btn_review, "Ouvrez un fichier CSV existant pour :\n- Corriger les erreurs de l'IA\n- Ajouter des prix\n- Valider l'inventaire")
        
        # Footer
        footer_frame = tk.Frame(root, bg="#f0f2f5", pady=10)
        footer_frame.pack(side="bottom", fill="x")
        
        self.lbl_ver = tk.Label(footer_frame, text=f"v{VERSION} ({BUILD_DATE}) - Régie des Quartiers", bg="#f0f2f5", fg="#999")
        self.lbl_ver.pack()

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

    def update_progress(self, current, total, filename):
        progress = (current / total) * 100
        self.root.after(0, lambda: self.progress_var.set(progress))
        self.root.after(0, lambda: self.lbl_status.config(text=f"Traitement de : {filename}"))

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
