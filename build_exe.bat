@echo off
rem Baut dist\RatioVoice\RatioVoice.exe (eigenstaendig, ohne installiertes Python lauffaehig).
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Bitte zuerst start.bat ausfuehren.
    pause
    exit /b 1
)
.venv\Scripts\python -m pip install pyinstaller || goto :error
.venv\Scripts\python -m PyInstaller --noconfirm --windowed --name RatioVoice ^
    --collect-all pedalboard --collect-all pyworld --collect-all sounddevice --collect-all soundfile ^
    --collect-all _sounddevice_data --collect-all _soundfile_data ^
    --hidden-import pkg_resources RatioVoice.py || goto :error
echo.
echo Fertig: dist\RatioVoice\RatioVoice.exe
pause
exit /b 0
:error
echo Build fehlgeschlagen.
pause
exit /b 1
