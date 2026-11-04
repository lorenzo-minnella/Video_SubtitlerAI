@echo off
REM ============================================================================
REM  Video SubtitlerAI - Build eseguibile Windows (.exe) con PyInstaller
REM  Eseguire su una macchina WINDOWS dentro la cartella del progetto.
REM
REM  NB: ffmpeg NON e' richiesto. faster-whisper decodifica l'audio con PyAV
REM      (il pacchetto "av"), che include gia' le librerie FFmpeg. Lo ZIP
REM      risultante e' autosufficiente: nessuna installazione sul PC utente.
REM ============================================================================
setlocal EnableDelayedExpansion

REM Spostati nella cartella dello script, così i file (requirements.txt, ecc.)
REM vengono sempre trovati, a prescindere da dove parte il doppio clic.
cd /d "%~dp0"

set APPNAME=VideoSubtitlerAI
set VERSION=3.3

REM Controllo di sicurezza: i file del progetto devono essere qui accanto.
if not exist "requirements.txt" (
    echo.
    echo [ERRORE] Non trovo "requirements.txt" in questa cartella:
    echo    %cd%
    echo.
    echo Probabile causa: lo ZIP e' stato estratto con una cartella dentro
    echo un'altra. Assicurati che "build_windows.bat" e "requirements.txt"
    echo siano NELLA STESSA cartella, poi rilancia.
    echo.
    pause
    exit /b 1
)

REM Individua il comando Python disponibile (python o py).
set PY=python
where python >nul 2>nul || set PY=py
%PY% --version >nul 2>nul
if errorlevel 1 (
    echo.
    echo [ERRORE] Python non trovato. Installa Python 3.10+ da python.org
    echo e durante l'installazione spunta "Add Python to PATH". Poi rilancia.
    echo.
    pause
    exit /b 1
)

echo [1/5] Creo/attivo l'ambiente virtuale...
if not exist ".venv" (
    %PY% -m venv .venv
)
call .venv\Scripts\activate.bat

echo [2/5] Installo le dipendenze...
python -m pip install --upgrade pip
pip install -r requirements.txt
REM Pillow + cairosvg servono solo per generare l'icona .ico (facoltativo)
pip install pillow cairosvg

echo [3/5] Genero l'icona .ico dal sorgente SVG (se disponibile)...
python tools\make_ico.py

echo [4/5] Compilo l'eseguibile con PyInstaller...
set ICONOPT=
if exist "assets\icon\icon.ico" set ICONOPT=--icon "assets\icon\icon.ico"

pyinstaller --noconfirm --clean ^
  --name "%APPNAME%" ^
  --windowed ^
  --onedir ^
  %ICONOPT% ^
  --collect-all faster_whisper ^
  --collect-all av ^
  --collect-all ctranslate2 ^
  --collect-all argostranslate ^
  --collect-all certifi ^
  --add-data "assets;assets" ^
  app_gui.py

if not exist "dist\%APPNAME%\%APPNAME%.exe" (
    echo.
    echo [ERRORE] Build non riuscita: %APPNAME%.exe non trovato in dist\.
    goto :end
)

echo [5/5] Creo lo ZIP di distribuzione...
set ZIPNAME=%APPNAME%-%VERSION%-win64.zip
if exist "%ZIPNAME%" del "%ZIPNAME%"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\%APPNAME%\*' -DestinationPath '%ZIPNAME%' -Force"

echo.
echo ============================================================================
echo  FATTO.
echo    Eseguibile : dist\%APPNAME%\%APPNAME%.exe
echo    Pacchetto  : %ZIPNAME%  (pronto per Google Drive)
echo  L'app e' autosufficiente: niente Python ne ffmpeg da installare sul PC.
echo ============================================================================

:end
endlocal
pause
