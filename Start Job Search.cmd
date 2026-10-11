@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Setting up your local Python environment...
    py -3 -m venv .venv
    if errorlevel 1 goto failed
)
if not exist ".venv\ready.txt" (
    ".venv\Scripts\python.exe" -m pip install -e .
    if errorlevel 1 goto failed
    echo ready>".venv\ready.txt"
)
if not exist ".venv\smart-ready.txt" (
    echo Installing free local semantic matching. First setup downloads the model.
    ".venv\Scripts\python.exe" -m pip install -r requirements-desktop.txt
    if errorlevel 1 goto failed
    ".venv\Scripts\python.exe" -c "from smart_search import load_model; load_model()"
    if errorlevel 1 goto failed
    echo ready>".venv\smart-ready.txt"
)
start "" ".venv\Scripts\pythonw.exe" desktop_search.py
exit /b 0
:failed
echo Setup failed. Install Python 3.10 or newer, then try again.
pause
exit /b 1
