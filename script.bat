@echo off
setlocal
set APP=src\main.py
set BIN=imagetobarcode

REM 1) venv
if not exist .venv (
  py -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install pyinstaller pillow pytesseract python-barcode qrcode

REM 2) check risorse
if not exist vendor\tesseract\tesseract.exe (
  echo Manca vendor\tesseract\tesseract.exe
  exit /b 1
)
if not exist vendor\tesseract\tessdata\eng.traineddata (
  echo Manca eng.traineddata
  exit /b 1
)
if not exist vendor\tesseract\tessdata\ita.traineddata (
  echo Manca ita.traineddata
  exit /b 1
)

REM 3) pulizia e build
rmdir /s /q build dist 2>nul
del /q *.spec 2>nul

pyinstaller --onefile --noconsole --clean --strip ^
  --name %BIN% ^
  --exclude-module numpy ^
  --exclude-module scipy ^
  --exclude-module pandas ^
  --exclude-module matplotlib ^
  --exclude-module torch ^
  --exclude-module tensorflow ^
  --hidden-import PIL._tkinter_finder ^
  --hidden-import tkinter ^
  --hidden-import qrcode ^
  --hidden-import qrcode.image.pil ^
  --hidden-import qrcode.image.svg ^
  --hidden-import qrcode.image.pure ^
  --collect-submodules barcode ^
  --add-data "vendor\tesseract\tesseract.exe;vendor\tesseract" ^
  --add-data "vendor\tesseract\tessdata;vendor\tesseract\tessdata" ^
  --add-data "vendor\fonts\DejaVuSans.ttf;fonts" ^
  --add-data "vendor\fonts\DejaVuSansMono.ttf;fonts" ^
  %APP%

echo.
echo Fatto: dist\%BIN%.exe
endlocal
