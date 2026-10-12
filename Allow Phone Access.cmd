@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -Command "Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"%~dp0allow_phone_access.ps1\"' -Wait"
pause
