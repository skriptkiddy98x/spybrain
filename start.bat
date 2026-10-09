@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0dist\SpyBrain\SpyBrain.exe" (
  start "" "%~dp0dist\SpyBrain\SpyBrain.exe"
  exit /b
)
if exist "%~dp0.venv\Scripts\pythonw.exe" (
  start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0app.py"
  exit /b
)
echo Set up the Python environment first, see README.md.
pause
