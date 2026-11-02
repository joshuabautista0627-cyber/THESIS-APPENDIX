@echo off
setlocal
cd /d "%~dp0calibration_gui"
set "DEMO_PY=.venv-demo\Scripts\python.exe"
if not exist "%DEMO_PY%" set "DEMO_PY=.venv\Scripts\python.exe"
if not exist "%DEMO_PY%" (
    echo Follow the Python 3.12 setup in BAURods_Live_Demo.md, then run this launcher again.
    pause
    exit /b 1
)
"%DEMO_PY%" -m baurods_demo %*
if errorlevel 1 (
    pause
    exit /b 1
)
