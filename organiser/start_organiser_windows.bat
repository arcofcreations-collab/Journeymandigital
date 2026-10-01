@echo off
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
start "" http://127.0.0.1:8765
%PY% -m msgorg.web
if errorlevel 1 (
  echo.
  echo Python 3 was not found. Install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^), then double-click this file again.
  pause
)
