from __future__ import annotations

import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageOps, ImageTk

from .. import codegen, ocr_service
from ..config import APP_TITLE, SUPPORTED_IMAGES
from ..utils import bundle_base_dir


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1100x680")
        self.minsize(900, 560)

        # immagini
        self.loaded_image: Image.Image | None = None
        self.tk_preview: ImageTk.PhotoImage | None = None
        self.generated_image: Image.Image | None = None
        self.tk_generated_preview: ImageTk.PhotoImage | None = None

        # stato UI
        self.lang_var = tk.StringVar(value="ita")
        self.w_var = tk.IntVar(value=1024)
        self.h_var = tk.IntVar(value=1024)

        self.btn_open: ttk.Button | None = None
        self.btn_ocr: ttk.Button | None = None
        self.ocr_progress: ttk.Progressbar | None = None
        self.nb: ttk.Notebook | None = None
        self.page2: ttk.Frame | None = None
        self._preview_job: str | None = None
        self._preview_enabled: bool = False  # anteprima disabilitata fino al click su "Esegui OCR"

        # webcam state
        self._webcam_window: tk.Toplevel | None = None
        self._webcam_canvas: tk.Canvas | None = None
        self._webcam_cap = None  # OpenCV capture object
        self._webcam_running: bool = False
        self._webcam_tk: ImageTk.PhotoImage | None = None
        self._webcam_last_frame = None

        self._build_ui()

    # ---------------- UI ----------------
    def _build_ui(self):
        top = ttk.Frame(self, padding=8)
        top.pack(side=tk.TOP, fill=tk.X)

        # Bottone per aprire l'immagine (sempre visibile in alto)
        self.btn_open = ttk.Button(top, text="Apri immagine", command=self.on_open_image)
        self.btn_open.pack(side=tk.LEFT)
        ttk.Button(top, text="Webcam", command=self.on_open_webcam).pack(side=tk.LEFT, padx=(6, 0))

        # Stato tesseract
        self.tess_status = ttk.Label(top, text=ocr_service.tesseract_status_text())
        self.tess_status.pack(side=tk.RIGHT)

        # Notebook passi
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True)

        # Pagina 1: Scegli/Acquisisci immagine
        page1 = ttk.Frame(self.nb, padding=12)
        self.nb.add(page1, text="1. Acquisisci etichetta")
        ttk.Label(page1, text="Anteprima etichetta").pack(anchor="w")
        self.canvas_in = tk.Canvas(page1, background="#f3f3f3", highlightthickness=1, height=420)
        self.canvas_in.pack(fill=tk.BOTH, expand=True, pady=(4, 8))
        self.canvas_in.bind("<Configure>", lambda e: self._render_input_preview())

        # Pagina 2: OCR + Generazione QR
        self.page2 = ttk.Frame(self.nb, padding=(8, 8, 8, 8))
        self.nb.add(self.page2, text="2. OCR e QR")
        bar = ttk.Frame(self.page2)
        bar.pack(fill=tk.X)
        self.btn_ocr = ttk.Button(bar, text="Esegui OCR", command=self.on_run_ocr)
        self.btn_ocr.pack(side=tk.LEFT)
        self.ocr_progress = ttk.Progressbar(bar, mode="indeterminate", length=140)
        ttk.Button(bar, text="Genera QR", command=self.on_generate_code).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(bar, text="Refresh", command=self.on_refresh_qr).pack(side=tk.LEFT, padx=(4, 0))

        # Impostazioni QR a destra della barra
        settings = ttk.Frame(bar)
        settings.pack(side=tk.RIGHT)
        ttk.Label(settings, text="Larghezza px:").pack(side=tk.LEFT)
        ttk.Spinbox(settings, from_=64, to=4096, width=6, textvariable=self.w_var).pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(settings, text="Altezza px:").pack(side=tk.LEFT)
        ttk.Spinbox(settings, from_=64, to=4096, width=6, textvariable=self.h_var).pack(side=tk.LEFT, padx=(4, 12))
        ttk.Button(settings, text="Salva immagine", command=self.on_save).pack(side=tk.LEFT)

        # Split orizzontale con testo (sinistra) e anteprima QR (destra)
        split = ttk.Panedwindow(self.page2, orient=tk.HORIZONTAL)
        split.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

        left = ttk.Frame(split, padding=(0, 0, 6, 0))
        right = ttk.Frame(split, padding=(6, 0, 0, 0))
        split.add(left, weight=3)
        split.add(right, weight=2)

        ttk.Label(
            left,
            text=(
                "Seleziona il testo desiderato e premi 'Genera QR'.\n"
                "Se non selezioni nulla, useremo tutto il testo."
            ),
            foreground="#555",
            wraplength=520,
            justify="left",
        ).pack(anchor="w", pady=(0, 4))

        self.text_widget = tk.Text(left, undo=True, wrap="word")
        self.text_widget.pack(fill=tk.BOTH, expand=True)
        self.text_widget.insert("1.0", "Il testo OCR apparirà qui.")
        self.text_widget.bind("<<Modified>>", self._on_text_modified)

        ttk.Label(right, text="Anteprima QR").pack(anchor="w", pady=(0, 4))
        self.canvas_out = tk.Canvas(right, background="#f9f9f9", highlightthickness=1)
        self.canvas_out.pack(fill=tk.BOTH, expand=True)
        self.canvas_out.bind("<Configure>", lambda e: self._render_output_preview())

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
    def on_open_image(self):
        patterns = ";".join(f"*{ext}" for ext in SUPPORTED_IMAGES)
        path = filedialog.askopenfilename(
            title="Seleziona immagine",
            filetypes=[("Immagini", patterns)],
            initialdir=str(bundle_base_dir()),
        )
        if not path:
            return
        try:
            img = Image.open(path)
            self.loaded_image = ImageOps.exif_transpose(img.convert("RGB"))
            self._after_new_input_image()
        except Exception as e:
            messagebox.showerror("Errore", str(e))

    # -------- Webcam --------
    def on_open_webcam(self):
        try:
            import cv2  # type: ignore
        except Exception:
            messagebox.showerror(
                "Webcam non disponibile",
                "OpenCV non trovato. Installa 'opencv-python' per usare la webcam.",
            )
            return

        if self._webcam_window and tk.Toplevel.winfo_exists(self._webcam_window):
            try:
                self._webcam_window.lift()
                return
            except Exception:
                pass

        self._webcam_window = tk.Toplevel(self)
        self._webcam_window.title("Webcam - Anteprima")
        self._webcam_window.protocol("WM_DELETE_WINDOW", self._close_webcam)
        self._webcam_window.resizable(False, False)

        wrap = ttk.Frame(self._webcam_window, padding=8)
        wrap.pack(fill=tk.BOTH, expand=True)

        self._webcam_canvas = tk.Canvas(wrap, width=640, height=480, background="#000")
        self._webcam_canvas.pack()

        controls = ttk.Frame(wrap)
        controls.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(controls, text="Avvia", command=self._start_webcam).pack(side=tk.LEFT)
        ttk.Button(controls, text="Ferma", command=self._stop_webcam).pack(side=tk.LEFT, padx=6)
        ttk.Button(controls, text="Scatta", command=self._capture_frame).pack(side=tk.LEFT)

        self._start_webcam()

    def _start_webcam(self):
        try:
            import cv2  # type: ignore
        except Exception:
            return
        if self._webcam_running:
            return
        try:
            self._webcam_cap = cv2.VideoCapture(0)
            if not self._webcam_cap or not self._webcam_cap.isOpened():
                raise RuntimeError("Impossibile aprire la webcam")
            self._webcam_running = True
            self._update_webcam_frame()
        except Exception as e:
            messagebox.showerror("Webcam", str(e))
            self._webcam_running = False

    def _stop_webcam(self):
        self._webcam_running = False
        cap = self._webcam_cap
        self._webcam_cap = None
        try:
            if cap is not None:
                cap.release()
        except Exception:
            pass

    def _close_webcam(self):
        self._stop_webcam()
        try:
            if self._webcam_window and tk.Toplevel.winfo_exists(self._webcam_window):
                self._webcam_window.destroy()
        except Exception:
            pass
        self._webcam_window = None
        self._webcam_canvas = None

    def _update_webcam_frame(self):
        if not self._webcam_running or self._webcam_cap is None or self._webcam_canvas is None:
            return
        try:
            import cv2  # type: ignore
        except Exception:
            return
        ret, frame = self._webcam_cap.read()
        if ret and frame is not None:
            try:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                self._webcam_last_frame = frame_rgb
                h, w, _ = frame_rgb.shape
                canvas_w = int(self._webcam_canvas.winfo_width() or 640)
                canvas_h = int(self._webcam_canvas.winfo_height() or 480)
                scale = min(canvas_w / w, canvas_h / h)
                disp_w, disp_h = int(w * scale), int(h * scale)
                import cv2 as _cv2  # type: ignore

                resized = _cv2.resize(frame_rgb, (disp_w, disp_h))
                img = Image.fromarray(resized)
                self._webcam_tk = ImageTk.PhotoImage(img)
                self._webcam_canvas.delete("all")
                self._webcam_canvas.create_image(
                    canvas_w // 2, canvas_h // 2, image=self._webcam_tk, anchor="center"
                )
            except Exception:
                pass
        if self._webcam_running and self._webcam_window and tk.Toplevel.winfo_exists(self._webcam_window):
            self._webcam_window.after(30, self._update_webcam_frame)

    def _capture_frame(self):
        if self._webcam_last_frame is None:
            messagebox.showwarning("Webcam", "Nessun frame disponibile. Avvia la webcam.")
            return
        img = Image.fromarray(self._webcam_last_frame)
        self.loaded_image = img.convert("RGB")
        self._after_new_input_image()
        self._close_webcam()

    # -------- OCR --------
    def on_run_ocr(self):
        if not self.loaded_image:
            messagebox.showwarning("Nessuna immagine", "Acquisisci o apri prima un'immagine.")
            return

        # Dialog lingua rapida
        lang = self._ask_language()
        if not lang:
            return
        self.lang_var.set(lang)

        def task():
            try:
                text = ocr_service.run_ocr(self.loaded_image, self.lang_var.get())
                self.after(0, self._finish_ocr, text)
            except Exception as e:
                self.after(0, self._fail_ocr, e)

        self._preview_enabled = True
        self._set_ocr_running(True)
        threading.Thread(target=task, daemon=True).start()

    def _finish_ocr(self, text: str):
        self.text_widget.delete("1.0", tk.END)
        self.text_widget.insert("1.0", text)
        self.text_widget.edit_reset()
        self._set_ocr_running(False)
        messagebox.showinfo("OCR completato", f"Lingua: {self.lang_var.get().upper()}")

    def _fail_ocr(self, err: Exception):
        self._set_ocr_running(False)
        messagebox.showerror("Errore OCR", str(err))

    def _set_ocr_running(self, running: bool):
        if self.btn_ocr is None or self.ocr_progress is None:
            return
        if running:
            self.btn_ocr.config(state=tk.DISABLED)
            self.ocr_progress.pack(side=tk.LEFT, padx=8)
            try:
                self.ocr_progress.start(10)
            except Exception:
                pass
            if self.btn_open:
                self.btn_open.config(state=tk.DISABLED)
        else:
            self.btn_ocr.config(state=tk.NORMAL)
            try:
                self.ocr_progress.stop()
            except Exception:
                pass
            self.ocr_progress.pack_forget()
            if self.btn_open:
                self.btn_open.config(state=tk.NORMAL)

    # -------- Generazione QR --------
    def on_generate_code(self):
        try:
            self._update_preview_from_text()
        except Exception as e:
            messagebox.showerror("Errore generazione QR", str(e))

    def _on_text_modified(self, event=None):
        try:
            self.text_widget.edit_modified(False)
        except Exception:
            pass

    def on_refresh_qr(self):
        self.generated_image = None
        try:
            self.canvas_out.delete("all")
        except Exception:
            pass

    def _update_preview_from_text(self):
        if not self._preview_enabled:
            try:
                self.canvas_out.delete("all")
            except Exception:
                pass
            return
        try:
            text = self.text_widget.selection_get().strip()
        except tk.TclError:
            text = self.text_widget.get("1.0", "end-1c").strip()
        if not text:
            self.on_refresh_qr()
            return
        w = int(self.w_var.get())
        h = int(self.h_var.get())
        if w <= 0 or h <= 0:
            return
        img = codegen.generate_qrcode(text, w, h)
        self.generated_image = img
        self._render_output_preview()

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

    def _render_output_preview(self):
        if not self.generated_image:
            return
        cw = int(self.canvas_out.winfo_width() or 300)
        ch = int(self.canvas_out.winfo_height() or 220)
        img = self.generated_image.copy()
        img.thumbnail((cw - 8, ch - 8))
        self.tk_generated_preview = ImageTk.PhotoImage(img)
        self.canvas_out.delete("all")
        self.canvas_out.create_image(cw // 2, ch // 2, image=self.tk_generated_preview, anchor="center")

    # ---- dialog lingua ----
    def _ask_language(self) -> str | None:
        dlg = tk.Toplevel(self)
        dlg.title("Seleziona lingua OCR")
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)

        ttk.Label(dlg, text="Seleziona lingua:").pack(padx=12, pady=(12, 6), anchor="w")
        display_values = ["Italiano", "Inglese"]
        combo = ttk.Combobox(dlg, values=display_values, state="readonly", width=12)
        combo.set("Italiano" if self.lang_var.get().lower().startswith("it") else "Inglese")
        combo.pack(padx=12, anchor="w")

        result: dict = {"lang": None}

        def ok():
            result["lang"] = self._normalize_lang(combo.get())
            dlg.destroy()

        def cancel():
            result["lang"] = None
            dlg.destroy()

        btns = ttk.Frame(dlg)
        btns.pack(fill=tk.X, padx=12, pady=12)
        ttk.Button(btns, text="Annulla", command=cancel).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(btns, text="OK", command=ok).pack(side=tk.RIGHT)

        dlg.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dlg.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dlg.winfo_height()) // 3
        dlg.geometry(f"+{x}+{y}")

        self.wait_window(dlg)
        return result["lang"]

    def _normalize_lang(self, value: str) -> str:
        v = (value or "").strip().lower()
        mapping = {
            "ita": "ita",
            "italiano": "ita",
            "italian": "ita",
            "it": "ita",
            "it-it": "ita",
            "eng": "eng",
            "inglese": "eng",
            "english": "eng",
            "en": "eng",
            "en-us": "eng",
        }
        if v in mapping:
            return mapping[v]
        if v.startswith("it"):
            return "ita"
        if v.startswith("en"):
            return "eng"
        return v or "eng"

    def on_save(self):
        if not self.generated_image:
            try:
                self._update_preview_from_text()
            except Exception as e:
                messagebox.showerror("Errore generazione QR", str(e))
                return
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

    def _goto_step2(self):
        if self.nb and self.page2:
            try:
                self.nb.select(self.page2)
            except Exception:
                pass

    def _after_new_input_image(self):
        self._render_input_preview()
        self._goto_step2()
        self._preview_enabled = False
        self.generated_image = None
        try:
            self.canvas_out.delete("all")
        except Exception:
            pass

