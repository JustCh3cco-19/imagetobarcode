# Lettore Etichette Alfanumeriche

Applicazione desktop (Tkinter) pensata per un banco di lavoro con PC Windows, telecamera rivolta verso il basso e supporto per etichette. Il flusso copre acquisizione (da webcam o da file), OCR e generazione del QR code dell'etichetta selezionata.

## Flusso operativo
1. Posiziona la confezione sotto la telecamera, etichetta rivolta verso l'alto.
2. Premi `Webcam` per avere l'anteprima; quando l'immagine e' a fuoco premi `Scatta`.
   - In alternativa usa `Apri immagine` per caricare un file.
3. Vai alla scheda "OCR e QR" e premi `Esegui OCR`, scegliendo la lingua (Italiano/Inglese).
4. Seleziona il testo desiderato nel riquadro centrale e premi `Genera QR`.
5. Il QR code appare a destra; puoi salvarlo con `Salva immagine`.
6. Con `Refresh` pulisci la finestra QR e riparti dal punto 1.

## Requisiti
- Python 3.10+
- Tesseract OCR installato (oppure fornito in `vendor/tesseract`).
- Librerie Python: `pillow`, `pytesseract`, `qrcode`, `opencv-python` (opzionale ma necessario per la webcam), `numpy`.

## Setup rapido
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install pillow pytesseract qrcode opencv-python numpy
```

## Avvio applicazione
```powershell
python -m src.main
```

## Creare l'eseguibile (PyInstaller, PowerShell)
```powershell
pyinstaller --clean --onefile --noconsole --name lettore-etichette `
  --hidden-import=PIL._tkinter_finder --hidden-import=tkinter `
  --hidden-import=qrcode --hidden-import=qrcode.image.pil `
  --hidden-import=cv2 --collect-binaries=cv2 `
  --add-binary "vendor\tesseract\tesseract.exe;." `
  --add-binary "vendor\tesseract\libtesseract-5.dll;." `
  --add-binary "vendor\tesseract\libleptonica-6.dll;." `
  --add-binary "vendor\tesseract\libcurl-4.dll;." `
  --add-binary "vendor\tesseract\libarchive-13.dll;." `
  --add-binary "vendor\tesseract\libtiff-6.dll;." `
  --add-binary "vendor\tesseract\libgcc_s_seh-1.dll;." `
  --add-binary "vendor\tesseract\libstdc++-6.dll;." `
  --add-data "vendor\tesseract\tessdata;tessdata" `
  src\main.py
```
Adatta i percorsi se il runtime Tesseract (o eventuali DLL aggiuntive) si trovano altrove.

## Note su Tesseract
L'app prova automaticamente: `vendor/tesseract/tesseract.exe`, `C:\Program Files\Tesseract-OCR\tesseract.exe`, `/usr/bin/tesseract`. Modifica `src/ocr_service.py` per aggiungere percorsi personalizzati o bundle dedicati.

