from __future__ import annotations

import sys
from pathlib import Path


def bundle_base_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def get_font_path() -> str | None:
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

