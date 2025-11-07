import os
import sys
import threading
from pathlib import Path
from io import BytesIO

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageOps

# Dipendenze: pip install pillow pytesseract python-barcode
import pytesseract
import barcode
from barcode.writer import ImageWriter


APP_TITLE = "OCR ➜ Code39 Generator"
SUPPORTED_IMAGES = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp")


def bundle_base_dir() -> Path:
    try:
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    except Exception:
        return Path(__file__).resolve().parent


def configure_embedded_tesseract():
    """Imposta automaticamente il percorso di Tesseract."""
    try:
        _ = pytesseract.get_tesseract_version()
        return
    except Exception:
        pass

    base = bundle_base_dir()
    candidates = [
        Path("/usr/bin/tesseract"),
        Path("/usr/local/bin/tesseract"),
        base / "tesseract",
        base / "vendor" / "tesseract" / "tesseract",
    ]
    for exe in candidates:
        if exe.exists():
            pytesseract.pytesseract.tesseract_cmd = str(exe)
            tessdata_candidates = [
                Path("/usr/share/tesseract-ocr/4.00/tessdata"),
                Path("/usr/share/tesseract-ocr/5/tessdata"),
                exe.parent / "tessdata",
            ]
            for td in tessdata_candidates:
                if td.is_dir():
                    os.environ["TESSDATA_PREFIX"] = str(td)
                    break
            break


configure_embedded_tesseract()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("950x620")
        self.minsize(820, 500)

        self.input_image_path: Path | None = None
        self.loaded_image: Image.Image | None = None
        self.tk_preview: ImageTk.PhotoImage | None = None
        self.generated_image: Image.Image | None = None
        self.tk_generated_preview: ImageTk.PhotoImage | None = None

        self.lang_var = tk.StringVar(value="eng")
        self._build_ui()

    # ---------------- UI ----------------
    def _build_ui(self):
        top = ttk.Frame(self, padding=8)
        top.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(top, text="Apri immagine…", command=self.on_open_image).pack(side=tk.LEFT)
        self.lang_btn = ttk.Button(top, text="Lingua: ENG", command=self.toggle_lang)
        self.lang_btn.pack(side=tk.LEFT, padx=10)
        self.tess_status = ttk.Label(top, text=self._tesseract_status_text())
        self.tess_status.pack(side=tk.RIGHT)

        main = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True)

        # --- Sinistra: immagine ---
        left = ttk.Frame(main, padding=8)
        main.add(left, weight=1)
        ttk.Label(left, text="Anteprima immagine").pack()
        self.canvas_in = tk.Canvas(left, background="#f3f3f3", highlightthickness=1, height=360)
        self.canvas_in.pack(fill=tk.BOTH, expand=True)

        # --- Centro: testo OCR ---
        center = ttk.Frame(main, padding=(8, 8, 8, 0))
        main.add(center, weight=1)

        # Barra strumenti testo
        bar = ttk.Frame(center)
        bar.pack(fill=tk.X)
        ttk.Button(bar, text="Esegui OCR", command=self.on_run_ocr).pack(side=tk.LEFT)
        ttk.Button(bar, text="↶ Annulla", command=lambda: self.safe_undo()).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="↷ Ripristina", command=lambda: self.safe_redo()).pack(side=tk.LEFT)

        # Text widget con undo abilitato
        self.text_widget = tk.Text(center, undo=True, wrap="word")
        self.text_widget.pack(fill=tk.BOTH, expand=True)
        self.text_widget.insert("1.0", "Testo OCR apparirà qui…")

        # Shortcuts Undo/Redo
        self.text_widget.bind("<Control-z>", lambda e: self.safe_undo())
        self.text_widget.bind("<Control-y>", lambda e: self.safe_redo())

        # --- Destra: generazione codice ---
        right = ttk.Frame(main, padding=8)
        main.add(right, weight=1)

        # Campi Larghezza e Altezza verticali
        self.w_var = tk.IntVar(value=800)
        self.h_var = tk.IntVar(value=240)
        ttk.Label(right, text="Larghezza px:").pack(anchor="w")
        ttk.Entry(right, width=10, textvariable=self.w_var).pack(anchor="w", pady=(0, 6))
        ttk.Label(right, text="Altezza px:").pack(anchor="w")
        ttk.Entry(right, width=10, textvariable=self.h_var).pack(anchor="w", pady=(0, 10))

        # Pulsante principale con wrapping automatico
        btn_code = tk.Button(
            right,
            text="Genera Code39 dal testo selezionato",
            command=self.on_generate_code39,
            wraplength=180,
            justify="center",
            font=("Segoe UI", 9, "bold"),
        )
        btn_code.pack(fill=tk.X, pady=6, ipadx=4, ipady=5)

        ttk.Button(right, text="Salva immagine…", command=self.on_save).pack(fill=tk.X)

        ttk.Label(right, text="Anteprima codice").pack(anchor="w", pady=(12, 6))
        self.canvas_out = tk.Canvas(right, background="#f9f9f9", highlightthickness=1, height=240)
        self.canvas_out.pack(fill=tk.BOTH, expand=False)

    # ---------------- Funzioni di utilità ----------------
    def _tesseract_status_text(self) -> str:
        try:
            ver = pytesseract.get_tesseract_version()
            return f"Tesseract: {ver}"
        except Exception:
            return "Tesseract: NON trovato"

    def safe_undo(self):
        """Evita errori 'nothing to undo'."""
        try:
            self.text_widget.edit_undo()
        except tk.TclError:
            pass

    def safe_redo(self):
        """Evita errori 'nothing to redo'."""
        try:
            self.text_widget.edit_redo()
        except tk.TclError:
            pass

    # ---------------- Logica ----------------
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
            self.input_image_path = Path(path)
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
                text = pytesseract.image_to_string(self.loaded_image, lang=self.lang_var.get()).strip()
                self.after(0, self._finish_ocr, text)
            except Exception as e:
                self.after(0, self._fail_ocr, e)

        threading.Thread(target=task, daemon=True).start()

    def _finish_ocr(self, text):
        self.text_widget.delete("1.0", tk.END)
        self.text_widget.insert("1.0", text)
        self.text_widget.edit_reset()
        messagebox.showinfo("OCR completato", f"Lingua: {self.lang_var.get().upper()}")

    def _fail_ocr(self, err):
        messagebox.showerror("Errore OCR", str(err))

    # -------- Generazione codice --------
    def on_generate_code39(self):
        """Genera un barcode Code39 dal testo selezionato."""
        try:
            selected_text = self.text_widget.selection_get().strip()
        except tk.TclError:
            selected_text = ""

        if not selected_text:
            messagebox.showwarning("Nessuna selezione", "Seleziona prima una parte di testo da convertire.")
            return

        allowed = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ -. $/+%"
        cleaned = "".join(ch for ch in selected_text.upper() if ch in allowed)

        if cleaned != selected_text.upper():
            messagebox.showinfo(
                "Testo adattato",
                "Alcuni caratteri non sono ammessi in Code39 e sono stati rimossi automaticamente.",
            )

        if not cleaned:
            messagebox.showerror("Errore", "Il testo non contiene caratteri validi per Code39.")
            return

        try:
            cls = barcode.get_barcode_class("code39")
            code = cls(cleaned, writer=ImageWriter())
            buf = BytesIO()
            code.write(buf, options={"write_text": True})
            buf.seek(0)
            img = Image.open(buf).convert("RGB")
            img = ImageOps.contain(img, (self.w_var.get(), self.h_var.get()))
            self.generated_image = img
            self._render_output_preview()
        except Exception as e:
            messagebox.showerror("Errore generazione", str(e))

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


if __name__ == "__main__":
    app = App()
    app.mainloop()
