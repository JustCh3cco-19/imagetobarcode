from __future__ import annotations

import os
import sys
from pathlib import Path

from PIL import Image
import pytesseract

from .utils import bundle_base_dir


def configure_embedded_tesseract() -> None:
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
        Path(r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe") if is_windows else Path("/usr/bin/tesseract"),
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
                Path(r"C:\\Program Files\\Tesseract-OCR\\tessdata") if is_windows else Path("/usr/share/tesseract-ocr/5/tessdata"),
                Path("/usr/share/tesseract-ocr/4.00/tessdata"),
            ):
                if td.is_dir():
                    os.environ["TESSDATA_PREFIX"] = str(td)
                    break
            pytesseract.get_tesseract_version()
            return


def tesseract_status_text() -> str:
    try:
        ver = pytesseract.get_tesseract_version()
        return f"Tesseract: {ver}"
    except Exception:
        return "Tesseract: NON trovato"


def run_ocr(image: Image.Image, lang: str) -> str:
    return pytesseract.image_to_string(image, lang=lang).strip()


# Configure on import for convenience
configure_embedded_tesseract()

