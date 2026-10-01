@echo off
title Message organiser
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% --version >nul 2>nul || (
  echo Python 3 is needed once. Install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^), then double-click this file again.
  pause & exit /b 1
)
echo Looking for your phone (unlock it and choose "File transfer" in its USB notification)...
for /f "usebackq delims=" %%L in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fetch_from_phone.ps1"`) do set RESULT=%%L
if "%RESULT%"=="NOPHONE" (
  echo No phone found. Unlock the phone, pull down notifications, tap the USB notification, choose "File transfer", then run this again.
) else if "%RESULT%"=="NOBACKUP" (
  echo The phone is connected but has no backup yet. On the phone open "SMS Backup ^& Restore" and tap "Back up now" ^(save to the phone^), then run this again.
) else if "%RESULT%"=="COPYFAILED" (
  echo Copying the backup from the phone did not finish. Keep the phone unlocked and run this again.
) else (
  echo Importing %RESULT% ...
  %PY% -m msgorg.cli import "%RESULT%" --skip-if-imported
)
echo.
echo Opening the organiser in your browser. Close this window to stop it.
start "" http://127.0.0.1:8765
%PY% -m msgorg.web
pause
