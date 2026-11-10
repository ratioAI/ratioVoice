@echo off
rem Richtet beim ersten Start eine virtuelle Umgebung ein und startet RatioVoice.
setlocal
cd /d "%~dp0"

rem Vorhandene Umgebung nur verwenden, wenn sie vollstaendig ist.
if exist .venv\Scripts\python.exe (
    .venv\Scripts\python -c "import pyworld, pedalboard, PySide6, sounddevice, soundfile" >nul 2>&1 && goto :run
    echo Vorhandene Umgebung ist unvollstaendig - wird neu eingerichtet ...
    rmdir /s /q .venv
)

rem RatioVoice braucht Python 3.11 bis 3.13: Fuer neuere Versionen gibt es die
rem Bibliothek pyworld noch nicht als fertiges Windows-Paket.
set PYVER=
for %%V in (3.13 3.12 3.11) do (
    if not defined PYVER (
        py -%%V -c "import sys" >nul 2>&1 && set PYVER=%%V
    )
)
if not defined PYVER (
    echo Kein Python 3.11 bis 3.13 gefunden - installiere Python 3.13 ueber den Python Install Manager ...
    py install 3.13
    py -3.13 -c "import sys" >nul 2>&1 && set PYVER=3.13
)
if not defined PYVER goto :nopython

echo Richte RatioVoice mit Python %PYVER% ein (einmalig, dauert ein paar Minuten) ...
py -%PYVER% -m venv .venv || goto :error
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt || goto :error

:run
start "" .venv\Scripts\pythonw RatioVoice.py
exit /b 0

:nopython
echo.
echo Es wurde kein Python 3.11 bis 3.13 gefunden und es liess sich nicht automatisch installieren.
echo Bitte den "Python Install Manager" von https://www.python.org/downloads/ installieren
echo und start.bat erneut ausfuehren.
pause
exit /b 1

:error
echo.
echo Die Einrichtung ist fehlgeschlagen (siehe Meldungen oben).
if exist .venv rmdir /s /q .venv
pause
exit /b 1
