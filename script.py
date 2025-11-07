import os
import sys
import threading
from pathlib import Path
from io import BytesIO

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageOps
import pytesseract
import barcode
from barcode.writer import ImageWriter
import qrcode

APP_TITLE = "OCR ➜ Code39/QR Generator"
SUPPORTED_IMAGES = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp")


def bundle_base_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def configure_embedded_tesseract():
    try:
        _ = pytesseract.get_tesseract_version()
        return
    except Exception:
        pass

    base = bundle_base_dir()
    is_windows = os.name == "nt"

    if getattr(sys, "frozen", False):
        exe = base / ("tesseract.exe" if is_windows else "tesseract")
        if exe.exists():
            pytesseract.pytesseract.tesseract_cmd = str(exe)
            os.environ["PATH"] = os.pathsep.join([str(exe.parent), os.environ.get("PATH", "")])
            td = base / "tessdata"
            if td.is_dir():
                os.environ["TESSDATA_PREFIX"] = str(td)
            pytesseract.get_tesseract_version()
            return

    candidates = [
        base / "vendor" / "tesseract" / ("tesseract.exe" if is_windows else "tesseract"),
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe") if is_windows else Path("/usr/bin/tesseract"),
        Path("/usr/local/bin/tesseract"),
    ]
    for exe in candidates:
        if exe.exists():
            pytesseract.pytesseract.tesseract_cmd = str(exe)
            os.environ["PATH"] = os.pathsep.join([str(exe.parent), os.environ.get("PATH", "")])
            for td in (
                exe.parent / "tessdata",
                base / "vendor" / "tesseract" / "tessdata",
                base / "tessdata",
                Path(r"C:\Program Files\Tesseract-OCR\tessdata") if is_windows else Path("/usr/share/tesseract-ocr/5/tessdata"),
                Path("/usr/share/tesseract-ocr/4.00/tessdata"),
            ):
                if td.is_dir():
                    os.environ["TESSDATA_PREFIX"] = str(td)
                    break
            pytesseract.get_tesseract_version()
            return


# ---- FONT per python-barcode ----
def get_font_path() -> str | None:
    """
    Restituisce il path di un font TTF incluso nel bundle.
    Metti ad es. 'DejaVuSansMono.ttf' in:
      - vendor/fonts/DejaVuSansMono.ttf   (in sviluppo)
      - <MEIPASS>/fonts/DejaVuSansMono.ttf (nel bundle)
    """
    base = bundle_base_dir()
    candidates = [
        base / "fonts" / "DejaVuSansMono.ttf",
        base / "fonts" / "DejaVuSans.ttf",
        base / "vendor" / "fonts" / "DejaVuSansMono.ttf",
        base / "vendor" / "fonts" / "DejaVuSans.ttf",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


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
        self.code_type_var = tk.StringVar(value="code39")
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
    def _tesseract_status_text(self) -> str:
        try:
            ver = pytesseract.get_tesseract_version()
            return f"Tesseract: {ver}"
        except Exception:
            return "Tesseract: NON trovato"

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

    # -------- Generazione codici --------
    def on_generate_code(self):
        if self.code_type_var.get() == "code39":
            self.on_generate_code39()
        else:
            self.on_generate_qrcode()

    def on_generate_code39(self):
        try:
            selected_text = self.text_widget.selection_get().strip()
        except tk.TclError:
            selected_text = ""

        if not selected_text:
            messagebox.showwarning("Nessuna selezione", "Seleziona prima una parte di testo da convertire.")
            return

        allowed = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ -. $/+%"
        cleaned = "".join(ch for ch in selected_text.upper() if ch in allowed)
        if not cleaned:
            messagebox.showerror("Errore", "Il testo non contiene caratteri validi per Code39.")
            return

        try:
            cls = barcode.get_barcode_class("code39")
            writer = ImageWriter()
            options = {"write_text": True}

            font_path = get_font_path()
            if font_path:
                options["font_path"] = font_path
            else:
                # se nessun font bundle, disattiva il testo per evitare l'errore "cannot open resource"
                options["write_text"] = False

            code = cls(cleaned, writer=writer)
            buf = BytesIO()
            code.write(buf, options=options)
            buf.seek(0)
            img = Image.open(buf).convert("RGB")
            img = ImageOps.contain(img, (self.w_var.get(), self.h_var.get()))
            self.generated_image = img
            self._render_output_preview()
        except Exception as e:
            messagebox.showerror("Errore generazione", str(e))

    def on_generate_qrcode(self):
        try:
            selected_text = self.text_widget.selection_get().strip()
        except tk.TclError:
            selected_text = ""

        if not selected_text:
            messagebox.showwarning("Nessuna selezione", "Seleziona prima una parte di testo da convertire.")
            return

        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(selected_text)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            img = img.convert("RGB")
            img = ImageOps.contain(img, (self.w_var.get(), self.h_var.get()))
            self.generated_image = img
            self._render_output_preview()
        except Exception as e:
            messagebox.showerror("Errore generazione QR", str(e))

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