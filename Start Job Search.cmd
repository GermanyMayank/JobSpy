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
start "" ".venv\Scripts\pythonw.exe" desktop_search.py
exit /b 0
:failed
echo Setup failed. Install Python 3.10 or newer, then try again.
pause
exit /b 1
