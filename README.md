# Lettore Etichette Alfanumeriche (webcam-feature)

Applicazione desktop Windows (Tkinter) per:
- Acquisire etichette tramite webcam o da file immagine
- Eseguire OCR (Tesseract) e mostrare il testo estratto
- Generare un QR Code dal testo selezionato
- Visualizzare il QR a destra e salvarlo su file
- Pulire rapidamente il riquadro QR con il tasto Refresh

## Dipendenze principali
- Python 3.10+
- Pillow
- pytesseract (con binari Tesseract installati o vendorizzati)
- qrcode
- (Opzionale) opencv-python per la webcam

## Avvio in sviluppo
```
python -m src.main
```

## Eseguibile (PyInstaller)
Esempio di comando (adatta i percorsi dei binari Tesseract presenti in `vendor/tesseract` se li includi nel bundle):
```
pyInstaller --clean --onefile --noconsole --name lettore-etichette \
  --hidden-import=PIL._tkinter_finder --hidden-import=tkinter \
  --hidden-import=qrcode --hidden-import=qrcode.image.pil \
  --add-binary "vendor\tesseract\tesseract.exe;." \
  --add-binary "vendor\tesseract\libtesseract-5.dll;." \
  --add-binary "vendor\tesseract\libleptonica-6.dll;." \
  --add-data   "vendor\tesseract\tessdata;tessdata"
```
Se vuoi usare la webcam anche da eseguibile, includi OpenCV (`opencv-python`).

## Flusso operativo
1) Posiziona la confezione sotto la telecamera (rivolta in basso) 
2) Apri l’app e premi "Webcam" per vedere l’anteprima; quando l’etichetta è a fuoco, premi "Scatta" (oppure usa "Apri immagine" per file)
3) Premi "Esegui OCR" e conferma la lingua: il testo appare nella colonna centrale
4) Seleziona il testo desiderato e premi "Genera QR" (senza selezione usa tutto il testo)
5) Vedi il QR nella finestra a destra e opzionalmente "Salva immagine"
6) Premi "Refresh" per pulire il riquadro del QR e ripartire dal punto 1

## Note su Tesseract
L’app tenta di rilevare automaticamente `tesseract.exe` in:
- `vendor/tesseract/` nel bundle
- `C:\\Program Files\\Tesseract-OCR\\tesseract.exe`
Puoi personalizzare in `src/ocr_service.py`.

