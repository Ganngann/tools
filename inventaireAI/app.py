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

class LauncherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Inventaire AI - Launcher")
        self.root.geometry("600x450")
        self.root.configure(bg="#f0f2f5")
        
        # Style
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("Big.TButton", font=("Arial", 14), padding=20)
        self.style.configure("Title.TLabel", font=("Arial", 24, "bold"), background="#f0f2f5", foreground="#333")
        self.style.configure("Sub.TLabel", font=("Arial", 12), background="#f0f2f5", foreground="#666")

        # Header
        header_frame = tk.Frame(root, bg="#f0f2f5", pady=40)
        header_frame.pack(fill="x")
        
        lbl_title = ttk.Label(header_frame, text="Inventaire AI", style="Title.TLabel")
        lbl_title.pack()
        
        lbl_sub = ttk.Label(header_frame, text="Choisissez une action pour commencer", style="Sub.TLabel")
        lbl_sub.pack(pady=(10, 0))

        # Buttons Frame
        btn_frame = tk.Frame(root, bg="#f0f2f5", pady=20)
        btn_frame.pack(expand=True)



        self.btn_scan = ttk.Button(btn_frame, text="🆕 Nouvel Inventaire\n(Scanner des photos)", style="Big.TButton", command=self.start_new_inventory)
        self.btn_scan.pack(fill="x", pady=10, ipadx=50)
        ToolTip(self.btn_scan, "Sélectionnez un dossier de photos.\nL'IA analysera chaque image pour créer un fichier Excel (CSV).")

        self.btn_review = ttk.Button(btn_frame, text="🛠️ Réviser / Corriger\n(Ouvrir un CSV)", style="Big.TButton", command=self.start_review)
        self.btn_review.pack(fill="x", pady=10, ipadx=50)
        ToolTip(self.btn_review, "Ouvrez un fichier CSV existant pour :\n- Corriger les erreurs de l'IA\n- Ajouter des prix\n- Valider l'inventaire")
        
        # Footer
        footer_frame = tk.Frame(root, bg="#f0f2f5", pady=10)
        footer_frame.pack(side="bottom", fill="x")
        lbl_ver = tk.Label(footer_frame, text="v1.0 - Régie des Quartiers", bg="#f0f2f5", fg="#999")
        lbl_ver.pack()

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
        
        lbl = tk.Label(self.popup, text="Analyse des images par l'IA...\nVeuillez patienter.", pady=10, font=("Arial", 11))
        lbl.pack()
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self.popup, orient="horizontal", length=300, mode="determinate", variable=self.progress_var)
        self.progress_bar.pack(pady=10)
        
        self.lbl_status = tk.Label(self.popup, text="Préparation...", fg="gray")
        self.lbl_status.pack()

        # Run in thread
        threading.Thread(target=self.run_process_inventory, args=(folder_selected,), daemon=True).start()

    def run_process_inventory(self, folder_path):
        try:
            csv_path = process_inventory(folder_path, progress_callback=self.update_progress)
            
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
