from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps
import barcode
from barcode.writer import ImageWriter
import qrcode

from .utils import get_font_path


def generate_code39(text: str, width: int, height: int) -> Image.Image:
    allowed = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ -. $/+%"
    cleaned = "".join(ch for ch in text.upper() if ch in allowed)
    if not cleaned:
        raise ValueError("Il testo non contiene caratteri validi per Code39.")

    cls = barcode.get_barcode_class("code39")
    writer = ImageWriter()
    options: dict = {"write_text": True}

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
    img = ImageOps.contain(img, (width, height))
    return img


def generate_qrcode(text: str, width: int, height: int) -> Image.Image:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(text)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    img = img.convert("RGB")
    img = ImageOps.contain(img, (width, height))
    return img

