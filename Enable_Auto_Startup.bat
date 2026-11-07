@echo off
title SARATHI Auto-Startup Setup
echo ===================================================
echo Enabling SARATHI Auto-Startup on Laptop Boot...
echo ===================================================

set SCRIPT_DIR=%~dp0
set TARGET_BAT=%SCRIPT_DIR%Launch_Sarathi.bat
set SHORTCUT_PATH=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\SARATHI.lnk

powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath = '%TARGET_BAT%'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.WindowStyle = 7; $s.Save()"

if exist "%SHORTCUT_PATH%" (
    echo [OK] SARATHI will now start automatically whenever your laptop boots up!
    echo It will run silently in the background and wake up whenever you say "Hey Sarathi".
) else (
    echo [ERROR] Could not create startup shortcut.
)
echo.
pause
