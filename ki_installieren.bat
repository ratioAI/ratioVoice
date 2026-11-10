@echo off
rem Installiert die optionale KI-Voice-Conversion (ONNX Runtime mit CUDA).
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Bitte zuerst start.bat ausfuehren.
    pause
    exit /b 1
)
.venv\Scripts\python -m pip install -r requirements-ki.txt
pause
