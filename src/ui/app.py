from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageOps, ImageTk

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

from .. import codegen, ocr_service
from ..config import APP_TITLE, SUPPORTED_IMAGES
from ..utils import bundle_base_dir


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("950x620")
        self.minsize(820, 500)

        # immagini
        self.loaded_image: Image.Image | None = None
        self.tk_preview: ImageTk.PhotoImage | None = None
        self.generated_image: Image.Image | None = None
        self.tk_generated_preview: ImageTk.PhotoImage | None = None

        # stato UI
        self.lang_var = tk.StringVar(value="italiano")
        # Solo QR code: rimosso il tipo codice
        self.w_var = tk.IntVar(value=1920)
        self.h_var = tk.IntVar(value=1080)

        self.btn_open: ttk.Button | None = None
        self.btn_ocr: ttk.Button | None = None
        self.lang_combo: ttk.Combobox | None = None  # non più mostrata; rimane per compatibilità
        self.ocr_progress: ttk.Progressbar | None = None
        self.nb: ttk.Notebook | None = None
        self.page2: ttk.Frame | None = None
        self._preview_job: str | None = None
        self._preview_enabled: bool = False  # anteprima disabilitata fino al click su "Esegui OCR"
        self.camera_combo: ttk.Combobox | None = None
        self.camera_status: ttk.Label | None = None
        self.btn_camera_preview: ttk.Button | None = None
        self.btn_camera_capture: ttk.Button | None = None
        self.btn_camera_stop: ttk.Button | None = None
        self._camera_sources: list[int] = []
        self._selected_camera = tk.IntVar(value=-1)
        self._camera_capture: cv2.VideoCapture | None = None
        self._camera_preview_job: str | None = None
        self._live_camera_image: Image.Image | None = None

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._refresh_cameras)

    # ---------------- UI ----------------
    def _build_ui(self):
        top = ttk.Frame(self, padding=8)
        top.pack(side=tk.TOP, fill=tk.X)

        # Bottone per aprire l'immagine (sempre visibile in alto)
        self.btn_open = ttk.Button(top, text="Apri immagine", command=self.on_open_image)
        self.btn_open.pack(side=tk.LEFT)

        # Nessun selettore lingua visibile: viene chiesto dopo "Esegui OCR".

        # Stato tesseract
        self.tess_status = ttk.Label(top, text=ocr_service.tesseract_status_text())
        self.tess_status.pack(side=tk.RIGHT)

        # Notebook con passi (1) Scegli immagine, (2) OCR & QR
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True)

        # Pagina 1: Scegli immagine
        page1 = ttk.Frame(self.nb, padding=12)
        self.nb.add(page1, text="1. Scegli immagine")
        cam_box = ttk.Labelframe(page1, text="Webcam", padding=(8, 6))
        cam_box.pack(fill=tk.X, pady=(0, 8))
        cam_row = ttk.Frame(cam_box)
        cam_row.pack(fill=tk.X)
        ttk.Label(cam_row, text="Sorgente:").pack(side=tk.LEFT)
        self.camera_combo = ttk.Combobox(cam_row, state="disabled", width=28)
        self.camera_combo.pack(side=tk.LEFT, padx=(6, 0))
        self.camera_combo.bind("<<ComboboxSelected>>", self._on_camera_selected)
        ttk.Button(cam_row, text="Aggiorna", command=self._refresh_cameras).pack(side=tk.LEFT, padx=4)
        cam_btns = ttk.Frame(cam_box)
        cam_btns.pack(fill=tk.X, pady=(6, 0))
        self.btn_camera_preview = ttk.Button(
            cam_btns, text="Webcam", command=self.on_start_camera_preview, state=tk.DISABLED
        )
        self.btn_camera_preview.pack(side=tk.LEFT)
        self.btn_camera_capture = ttk.Button(
            cam_btns, text="Scatta", command=self.on_capture_from_camera, state=tk.DISABLED
        )
        self.btn_camera_capture.pack(side=tk.LEFT, padx=4)
        self.btn_camera_stop = ttk.Button(
            cam_btns, text="Chiudi", command=self._stop_camera_stream, state=tk.DISABLED
        )
        self.btn_camera_stop.pack(side=tk.LEFT)
        self.camera_status = ttk.Label(cam_box, text="Inizializzazione webcam...")
        self.camera_status.pack(anchor="w", pady=(4, 0))
        ttk.Label(page1, text="Anteprima immagine").pack(anchor="w")
        self.canvas_in = tk.Canvas(page1, background="#f3f3f3", highlightthickness=1, height=380)
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
        ttk.Button(bar, text="Annulla", command=lambda: self.safe_undo()).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Ripristina", command=lambda: self.safe_redo()).pack(side=tk.LEFT)

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

        # Sinistra: hint + editor testo
        ttk.Label(
            left,
            text=(
                "Suggerimento: seleziona una parte di testo per creare un QR solo di quella selezione; "
                "se non selezioni nulla verrà usato tutto il testo."
            ),
            foreground="#555",
            wraplength=520,
            justify="left",
        ).pack(anchor="w", pady=(0, 4))

        self.text_widget = tk.Text(left, undo=True, wrap="word")
        self.text_widget.pack(fill=tk.BOTH, expand=True)
        self.text_widget.insert("1.0", "Il testo OCR apparirà qui.")
        self.text_widget.bind("<Control-z>", lambda e: self.safe_undo())
        self.text_widget.bind("<Control-y>", lambda e: self.safe_redo())
        # Aggiorna anteprima quando il testo o la selezione cambia
        self.text_widget.bind("<<Modified>>", self._on_text_modified)
        self.text_widget.bind("<KeyRelease>", lambda e: self._schedule_preview_update())
        self.text_widget.bind("<ButtonRelease-1>", lambda e: self._schedule_preview_update())

        # Aggiorna anteprima quando cambiano le dimensioni desiderate
        self.w_var.trace_add("write", lambda *args: self._schedule_preview_update())
        self.h_var.trace_add("write", lambda *args: self._schedule_preview_update())

        # Destra: anteprima QR
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
    def toggle_lang(self):
        # mantenuta per retro-compatibilità; ora si usa la combobox
        new_lang = "ita" if self.lang_var.get() == "eng" else "eng"
        self.lang_var.set(new_lang)
        if self.lang_combo:
            self.lang_combo.set(new_lang)

    def on_open_image(self):
        self._stop_camera_stream()
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

    def _after_new_input_image(self):
        self._render_input_preview()
        self._goto_step2()
        self._preview_enabled = False
        self.generated_image = None
        if hasattr(self, "canvas_out"):
            try:
                self.canvas_out.delete("all")
            except Exception:
                pass

    def _render_input_preview(self):
        self._draw_input_preview(self.loaded_image)

    def _draw_input_preview(self, image: Image.Image | None):
        canvas = getattr(self, "canvas_in", None)
        if not canvas:
            return
        if not image:
            try:
                canvas.delete("all")
            except Exception:
                pass
            self.tk_preview = None
            return
        cw = int(canvas.winfo_width() or 300)
        ch = int(canvas.winfo_height() or 300)
        img = image.copy()
        img.thumbnail((cw - 8, ch - 8))
        self.tk_preview = ImageTk.PhotoImage(img)
        canvas.delete("all")
        canvas.create_image(cw // 2, ch // 2, image=self.tk_preview, anchor="center")

    def on_run_ocr(self):
        if not self.loaded_image:
            messagebox.showwarning("Nessuna immagine", "Apri prima un'immagine.")
            return

        # Chiedi la lingua subito dopo il click
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

        # Abilita l'anteprima solo dopo che l'utente ha avviato l'OCR
        self._preview_enabled = True
        self._set_ocr_running(True)
        threading.Thread(target=task, daemon=True).start()

    def _finish_ocr(self, text: str):
        self.text_widget.delete("1.0", tk.END)
        self.text_widget.insert("1.0", text)
        self.text_widget.edit_reset()
        self._set_ocr_running(False)
        messagebox.showinfo("OCR completato", f"Lingua: {self.lang_var.get().upper()}")
        # Aggiorna subito l'anteprima con il testo ottenuto
        self._schedule_preview_update(delay_ms=0)

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
            # nessun selettore lingua visibile da disabilitare
            if self.btn_open:
                self.btn_open.config(state=tk.DISABLED)
        else:
            self.btn_ocr.config(state=tk.NORMAL)
            try:
                self.ocr_progress.stop()
            except Exception:
                pass
            self.ocr_progress.pack_forget()
            # nessun selettore lingua visibile da riabilitare
            if self.btn_open:
                self.btn_open.config(state=tk.NORMAL)

    # -------- Generazione codici --------
    def on_generate_code(self):
        # Manteniamo questo metodo per compatibilità: aggiorna solo l'anteprima
        try:
            self._update_preview_from_text()
        except Exception as e:
            messagebox.showerror("Errore generazione QR", str(e))

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

    def _on_text_modified(self, event=None):
        # reset flag modified e programma update
        try:
            self.text_widget.edit_modified(False)
        except Exception:
            pass
        self._schedule_preview_update()

    def _schedule_preview_update(self, delay_ms: int = 350):
        # Debounce per evitare rigenerazioni continue mentre si scrive
        if not self._preview_enabled:
            return
        if self._preview_job:
            try:
                self.after_cancel(self._preview_job)
            except Exception:
                pass
        self._preview_job = self.after(delay_ms, self._safe_update_preview)

    def _safe_update_preview(self):
        self._preview_job = None
        if not self._preview_enabled:
            return
        try:
            self._update_preview_from_text()
        except Exception:
            # non disturbare l'utente con errori durante la digitazione
            pass

    def _update_preview_from_text(self):
        if not self._preview_enabled:
            # svuota l'anteprima finché non si clicca "Esegui OCR"
            try:
                self.canvas_out.delete("all")
            except Exception:
                pass
            return
        # Usa selezione se presente, altrimenti tutto il testo
        try:
            text = self.text_widget.selection_get().strip()
        except tk.TclError:
            text = self.text_widget.get("1.0", "end-1c").strip()
        if not text:
            # Svuota anteprima
            self.generated_image = None
            self.canvas_out.delete("all")
            return
        w = int(self.w_var.get())
        h = int(self.h_var.get())
        if w <= 0 or h <= 0:
            return
        img = codegen.generate_qrcode(text, w, h)
        self.generated_image = img
        self._render_output_preview()

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
        # centra il dialog sulla finestra principale
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
        # default fallback: detect prefix or return original
        if v in mapping:
            return mapping[v]
        if v.startswith("it"):
            return "ita"
        if v.startswith("en"):
            return "eng"
        return v or "eng"

    def on_save(self):
        if not self.generated_image:
            # prova a generare da testo corrente
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

    # dopo apertura immagine, passa automaticamente alla pagina 2
    def _goto_step2(self):
        if self.nb and self.page2:
            try:
                self.nb.select(self.page2)
            except Exception:
                pass

    # -------- Webcam --------
    def _set_camera_status(self, text: str):
        if self.camera_status:
            self.camera_status.config(text=text)

    def _set_camera_idle(self, available: bool):
        state_preview = tk.NORMAL if available else tk.DISABLED
        if self.btn_camera_preview:
            self.btn_camera_preview.config(state=state_preview)
        if self.btn_camera_capture:
            self.btn_camera_capture.config(state=tk.DISABLED)
        if self.btn_camera_stop:
            self.btn_camera_stop.config(state=tk.DISABLED)

    def _set_camera_running(self):
        if self.btn_camera_preview:
            self.btn_camera_preview.config(state=tk.DISABLED)
        if self.btn_camera_capture:
            self.btn_camera_capture.config(state=tk.NORMAL)
        if self.btn_camera_stop:
            self.btn_camera_stop.config(state=tk.NORMAL)

    def _detect_cameras(self, max_devices: int = 6) -> list[int]:
        if cv2 is None:
            return []
        detected: list[int] = []
        backend = getattr(cv2, "CAP_DSHOW", getattr(cv2, "CAP_ANY", 0))
        for idx in range(max_devices):
            cap = None
            try:
                cap = cv2.VideoCapture(idx, backend)
                if cap and cap.isOpened():
                    detected.append(idx)
            except Exception:
                continue
            finally:
                if cap:
                    cap.release()
        return detected

    def _refresh_cameras(self):
        self._stop_camera_stream()
        if not self.camera_combo:
            return
        if cv2 is None:
            self.camera_combo.config(values=["OpenCV non disponibile"], state="disabled")
            self.camera_combo.set("OpenCV non disponibile")
            self._set_camera_status("Installa opencv-python per usare la webcam.")
            self._set_camera_idle(False)
            return
        sources = self._detect_cameras()
        self._camera_sources = sources
        if sources:
            values = [f"Camera {idx}" for idx in sources]
            self.camera_combo.config(values=values, state="readonly")
            self.camera_combo.current(0)
            self._selected_camera.set(sources[0])
            self._set_camera_status(f"Camere rilevate: {len(sources)}")
            self._set_camera_idle(True)
        else:
            self.camera_combo.config(values=["Nessuna camera"], state="disabled")
            self.camera_combo.set("Nessuna camera")
            self._selected_camera.set(-1)
            self._set_camera_status("Nessuna camera rilevata")
            self._set_camera_idle(False)

    def _on_camera_selected(self, event=None):
        if not self.camera_combo:
            return
        idx = self.camera_combo.current()
        if 0 <= idx < len(self._camera_sources):
            selected = self._camera_sources[idx]
            self._selected_camera.set(selected)
            self._set_camera_status(f"Camera selezionata: {selected}")
        else:
            self._selected_camera.set(-1)
        if self._camera_capture:
            self._stop_camera_stream()

    def _get_selected_camera_index(self) -> int | None:
        idx = self._selected_camera.get()
        return idx if idx >= 0 else None

    def on_start_camera_preview(self):
        if cv2 is None:
            messagebox.showerror("Webcam", "Installa il pacchetto opencv-python per usare la webcam.")
            return
        idx = self._get_selected_camera_index()
        if idx is None:
            messagebox.showwarning("Webcam", "Seleziona una camera prima di avviare l'anteprima.")
            return
        self._start_camera_stream(idx)

    def _start_camera_stream(self, index: int):
        if cv2 is None:
            return
        self._stop_camera_stream()
        backend = getattr(cv2, "CAP_DSHOW", getattr(cv2, "CAP_ANY", 0))
        try:
            cap = cv2.VideoCapture(index, backend)
        except Exception as exc:
            messagebox.showerror("Webcam", f"Errore apertura camera {index}: {exc}")
            return
        if not cap or not cap.isOpened():
            if cap:
                cap.release()
            messagebox.showerror("Webcam", f"Impossibile aprire la camera {index}.")
            return
        self._camera_capture = cap
        self._set_camera_running()
        self._set_camera_status(f"Anteprima attiva su camera {index}")
        self._schedule_camera_frame()

    def _schedule_camera_frame(self):
        if cv2 is None or not self._camera_capture:
            return
        ok, frame = self._camera_capture.read()
        if not ok:
            self._stop_camera_stream("Errore lettura webcam")
            messagebox.showwarning("Webcam", "Impossibile leggere frame dalla webcam.")
            return
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self._live_camera_image = Image.fromarray(frame)
        self._draw_input_preview(self._live_camera_image)
        self._camera_preview_job = self.after(40, self._schedule_camera_frame)

    def _stop_camera_stream(self, status: str | None = None):
        was_running = self._camera_capture is not None or self._camera_preview_job is not None
        if self._camera_preview_job:
            try:
                self.after_cancel(self._camera_preview_job)
            except Exception:
                pass
            self._camera_preview_job = None
        if self._camera_capture:
            try:
                self._camera_capture.release()
            except Exception:
                pass
            self._camera_capture = None
        self._live_camera_image = None
        available = bool(self._camera_sources) and cv2 is not None
        self._set_camera_idle(available)
        if status:
            self._set_camera_status(status)
        elif was_running:
            self._set_camera_status("Webcam ferma")
        self._render_input_preview()

    def on_capture_from_camera(self):
        if self._live_camera_image is None:
            messagebox.showwarning("Webcam", "Avvia la webcam e attendi che compaia l'anteprima.")
            return
        self.loaded_image = self._live_camera_image.copy()
        self._stop_camera_stream("Immagine catturata dalla webcam")
        self._after_new_input_image()

    def _on_close(self):
        self._stop_camera_stream()
        try:
            self.destroy()
        except Exception:
            pass
