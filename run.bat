@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment is missing. Running setup first...
  call setup.bat
  if errorlevel 1 exit /b 1
)
echo ======================================================
echo   Pixel Forensics Workbench
echo   Local URL: http://127.0.0.1:5000
echo   Press Ctrl+C in this window to stop.
echo ======================================================
start "" cmd /c "timeout /t 2 /nobreak ^>nul ^& start http://127.0.0.1:5000"
".venv\Scripts\python.exe" app.py
pause
