@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
    if errorlevel 1 goto failed
)
if not exist ".venv\ready.txt" (
    ".venv\Scripts\python.exe" -m pip install -e .
    if errorlevel 1 goto failed
    echo ready>".venv\ready.txt"
)
".venv\Scripts\python.exe" -c "import qrcode; import PIL" 2>nul
if errorlevel 1 (
    ".venv\Scripts\python.exe" -m pip install -r requirements-phone.txt
    if errorlevel 1 goto failed
)
echo Keep this window open while using JobSpy on your phone.
".venv\Scripts\python.exe" phone_server.py
if errorlevel 1 goto failed
exit /b 0
:failed
echo Phone access could not start. Check the message above.
pause
exit /b 1
