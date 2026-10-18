@echo off
setlocal
cd /d "%~dp0"
echo ======================================================
echo   Pixel Forensics Workbench - Environment Setup
echo ======================================================
where py >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python Launcher "py" was not found.
  echo Install Python 3.10 or newer from https://www.python.org/downloads/windows/
  echo Enable "Add Python to PATH" during installation, then retry.
  pause
  exit /b 1
)
py -3 --version
if errorlevel 1 (
  echo [ERROR] Python 3 was not found. Install Python 3.10 or newer.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 (echo [ERROR] Could not create virtual environment.& pause & exit /b 1)
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (echo [ERROR] pip upgrade failed. Check your internet connection.& pause & exit /b 1)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (echo [ERROR] Dependency installation failed. See the output above.& pause & exit /b 1)
echo.
echo [SUCCESS] Setup complete. Double-click run.bat to start the app.
pause
