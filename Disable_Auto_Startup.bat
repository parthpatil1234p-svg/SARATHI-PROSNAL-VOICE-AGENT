@echo off
title SARATHI Auto-Startup Removal
echo ===================================================
echo Disabling SARATHI Auto-Startup on Laptop Boot...
echo ===================================================

set SHORTCUT_PATH=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\SARATHI.lnk

if exist "%SHORTCUT_PATH%" (
    del /f /q "%SHORTCUT_PATH%"
    echo [OK] SARATHI Auto-Startup has been disabled.
) else (
    echo [INFO] SARATHI was not set to auto-start.
)
echo.
pause
