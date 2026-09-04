@echo off
REM ============================================================
REM Academic Paper Search Engine - Windows one-click launcher
REM Double-click to start. Open http://127.0.0.1:5000 in browser.
REM ============================================================
cd /d "%~dp0"

REM Use a writable temp dir inside the project (sandbox-friendly)
if not exist ".pip-tmp" mkdir ".pip-tmp"
set "TMP=%~dp0.pip-tmp"
set "TEMP=%~dp0.pip-tmp"

REM Find a usable python interpreter
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"
if not defined PY set "PY=python"

echo [START] Using interpreter: %PY%
echo [START] First run may auto-fetch papers from arXiv (1-3 min)...
"%PY%" run.py

echo.
echo [INFO] Server stopped. Press any key to close...
pause >nul
