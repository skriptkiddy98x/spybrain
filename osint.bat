@echo off
setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if "%~1"=="" (
  call "%~dp0start.bat"
  exit /b
)
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo The Python environment is missing. Use start.bat for the desktop app.
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0osinthub.py" %*
exit /b %errorlevel%
