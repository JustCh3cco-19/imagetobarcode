from __future__ import annotations

from PIL import Image, ImageOps
import qrcode


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

