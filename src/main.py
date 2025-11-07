from __future__ import annotations

import sys
from pathlib import Path

# Permette di eseguire sia `python -m src.main` sia `python src/main.py`
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ui.app import App


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
