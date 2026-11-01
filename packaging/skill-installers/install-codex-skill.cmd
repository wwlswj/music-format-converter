@echo off
setlocal
set "CLI=%LOCALAPPDATA%\Programs\ShaoLv\music-converter.exe"
if not exist "%CLI%" set "CLI=music-converter"
"%CLI%" skill install --target codex
if errorlevel 1 (
    echo Failed to install the Codex Skill.
    pause
    exit /b 1
)
echo Codex Skill installed.
timeout /t 2 >nul

