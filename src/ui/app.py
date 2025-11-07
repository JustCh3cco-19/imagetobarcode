from __future__ import annotations

import threading
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageOps

from ..config import APP_TITLE
from ..utils import bundle_base_dir
from .. import ocr_service
from .. import codegen


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("950x620")
        self.minsize(820, 500)

        self.loaded_image: Image.Image | None = None
        self.tk_preview: ImageTk.PhotoImage | None = None
        self.generated_image: Image.Image | None = None
        self.tk_generated_preview: ImageTk.PhotoImage | None = None

        self.lang_var = tk.StringVar(value="eng")
        self.code_type_var = tk.StringVar(value="code39")
        self._build_ui()

    # ---------------- UI ----------------
    def _build_ui(self):
        top = ttk.Frame(self, padding=8)
        top.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(top, text="Apri immagine…", command=self.on_open_image).pack(side=tk.LEFT)
        self.lang_btn = ttk.Button(top, text="Lingua: ENG", command=self.toggle_lang)
        self.lang_btn.pack(side=tk.LEFT, padx=10)
        self.tess_status = ttk.Label(top, text=ocr_service.tesseract_status_text())
        self.tess_status.pack(side=tk.RIGHT)

        main = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True)

        # Sinistra
        left = ttk.Frame(main, padding=8)
        main.add(left, weight=1)
        ttk.Label(left, text="Anteprima immagine").pack()
        self.canvas_in = tk.Canvas(left, background="#f3f3f3", highlightthickness=1, height=360)
        self.canvas_in.pack(fill=tk.BOTH, expand=True)

        # Centro
        center = ttk.Frame(main, padding=(8, 8, 8, 0))
        main.add(center, weight=1)
        bar = ttk.Frame(center)
        bar.pack(fill=tk.X)
        ttk.Button(bar, text="Esegui OCR", command=self.on_run_ocr).pack(side=tk.LEFT)
        ttk.Button(bar, text="↶ Annulla", command=lambda: self.safe_undo()).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="↷ Ripristina", command=lambda: self.safe_redo()).pack(side=tk.LEFT)
        self.text_widget = tk.Text(center, undo=True, wrap="word")
        self.text_widget.pack(fill=tk.BOTH, expand=True)
        self.text_widget.insert("1.0", "Testo OCR apparirà qui…")
        self.text_widget.bind("<Control-z>", lambda e: self.safe_undo())
        self.text_widget.bind("<Control-y>", lambda e: self.safe_redo())

        # Destra
        right = ttk.Frame(main, padding=8)
        main.add(right, weight=1)

        # Selezione tipo codice
        ttk.Label(right, text="Tipo codice:").pack(anchor="w")
        code_frame = ttk.Frame(right)
        code_frame.pack(anchor="w", pady=(0, 10))
        ttk.Radiobutton(code_frame, text="Code39", variable=self.code_type_var, value="code39").pack(side=tk.LEFT)
        ttk.Radiobutton(code_frame, text="QR Code", variable=self.code_type_var, value="qrcode").pack(side=tk.LEFT, padx=10)

        self.w_var = tk.IntVar(value=1920)
        self.h_var = tk.IntVar(value=1080)
        ttk.Label(right, text="Larghezza px:").pack(anchor="w")
        ttk.Entry(right, width=10, textvariable=self.w_var).pack(anchor="w", pady=(0, 6))
        ttk.Label(right, text="Altezza px:").pack(anchor="w")
        ttk.Entry(right, width=10, textvariable=self.h_var).pack(anchor="w", pady=(0, 10))
        tk.Button(
            right,
            text="Genera codice dal testo selezionato",
            command=self.on_generate_code,
            wraplength=180,
            justify="center",
            font=("Segoe UI", 9, "bold"),
        ).pack(fill=tk.X, pady=6, ipadx=4, ipady=5)
        ttk.Button(right, text="Salva immagine…", command=self.on_save).pack(fill=tk.X)
        ttk.Label(right, text="Anteprima codice").pack(anchor="w", pady=(12, 6))
        self.canvas_out = tk.Canvas(right, background="#f9f9f9", highlightthickness=1, height=240)
        self.canvas_out.pack(fill=tk.BOTH, expand=False)

    # -------- util --------
    def safe_undo(self):
        try:
            self.text_widget.edit_undo()
        except tk.TclError:
            pass

    def safe_redo(self):
        try:
            self.text_widget.edit_redo()
        except tk.TclError:
            pass

    # -------- logica --------
    def toggle_lang(self):
        new_lang = "ita" if self.lang_var.get() == "eng" else "eng"
        self.lang_var.set(new_lang)
        self.lang_btn.config(text=f"Lingua: {new_lang.upper()}")

    def on_open_image(self):
        path = filedialog.askopenfilename(
            title="Seleziona immagine",
            filetypes=[("Immagini", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp")],
            initialdir=str(bundle_base_dir()),
        )
        if not path:
            return
        try:
            img = Image.open(path)
            self.loaded_image = ImageOps.exif_transpose(img.convert("RGB"))
            self._render_input_preview()
        except Exception as e:
            messagebox.showerror("Errore", str(e))

    def _render_input_preview(self):
        if not self.loaded_image:
            return
        cw = int(self.canvas_in.winfo_width() or 300)
        ch = int(self.canvas_in.winfo_height() or 300)
        img = self.loaded_image.copy()
        img.thumbnail((cw - 8, ch - 8))
        self.tk_preview = ImageTk.PhotoImage(img)
        self.canvas_in.delete("all")
        self.canvas_in.create_image(cw // 2, ch // 2, image=self.tk_preview, anchor="center")

    def on_run_ocr(self):
        if not self.loaded_image:
            messagebox.showwarning("Nessuna immagine", "Apri prima un'immagine.")
            return

        def task():
            try:
                text = ocr_service.run_ocr(self.loaded_image, self.lang_var.get())
                self.after(0, self._finish_ocr, text)
            except Exception as e:
                self.after(0, self._fail_ocr, e)

        threading.Thread(target=task, daemon=True).start()

    def _finish_ocr(self, text: str):
        self.text_widget.delete("1.0", tk.END)
        self.text_widget.insert("1.0", text)
        self.text_widget.edit_reset()
        messagebox.showinfo("OCR completato", f"Lingua: {self.lang_var.get().upper()}")

    def _fail_ocr(self, err: Exception):
        messagebox.showerror("Errore OCR", str(err))

    # -------- Generazione codici --------
    def on_generate_code(self):
        try:
            selected_text = self.text_widget.selection_get().strip()
        except tk.TclError:
            selected_text = ""

        if not selected_text:
            messagebox.showwarning("Nessuna selezione", "Seleziona prima una parte di testo da convertire.")
            return

        try:
            if self.code_type_var.get() == "code39":
                img = codegen.generate_code39(selected_text, self.w_var.get(), self.h_var.get())
            else:
                img = codegen.generate_qrcode(selected_text, self.w_var.get(), self.h_var.get())
            self.generated_image = img
            self._render_output_preview()
        except Exception as e:
            title = "Errore generazione" if self.code_type_var.get() == "code39" else "Errore generazione QR"
            messagebox.showerror(title, str(e))

    def _render_output_preview(self):
        if not self.generated_image:
            return
        cw = int(self.canvas_out.winfo_width() or 300)
        ch = int(self.canvas_out.winfo_height() or 300)
        img = self.generated_image.copy()
        img.thumbnail((cw - 8, ch - 8))
        self.tk_generated_preview = ImageTk.PhotoImage(img)
        self.canvas_out.delete("all")
        self.canvas_out.create_image(cw // 2, ch // 2, image=self.tk_generated_preview, anchor="center")

    def on_save(self):
        if not self.generated_image:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg;*.jpeg")],
        )
        if not path:
            return
        self.generated_image.save(path)
        messagebox.showinfo("Salvato", path)
