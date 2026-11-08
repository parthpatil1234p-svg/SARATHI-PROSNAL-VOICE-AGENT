@echo off
title SARATHI Auto-Startup Setup
echo ===================================================
echo Enabling SARATHI Auto-Startup on Laptop Boot...
echo ===================================================

set SCRIPT_DIR=%~dp0
set TARGET_VBS=%SCRIPT_DIR%Launch_Sarathi_Background.vbs
set SHORTCUT_PATH=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\SARATHI.lnk

if not exist "%TARGET_VBS%" (
    set TARGET_VBS=%SCRIPT_DIR%Launch_Sarathi.bat
)

powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath = 'wscript.exe'; $s.Arguments = '\"%TARGET_VBS%\"'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.WindowStyle = 7; $s.Save()"

rem Also set Windows Registry Run Key for redundancy
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "SARATHI_AI_ASSISTANT" /t REG_SZ /d "wscript.exe \"%TARGET_VBS%\"" /f >nul 2>&1

if exist "%SHORTCUT_PATH%" (
    echo [OK] SARATHI will now start automatically whenever your laptop boots up!
    echo It runs silently in the background and automatically wakes up when you say "Hey Sarathi".
) else (
    echo [ERROR] Could not create startup shortcut.
)
echo.
pause
