@echo off
setlocal
set "CLI=%LOCALAPPDATA%\Programs\ShaoLv\music-converter.exe"
if not exist "%CLI%" set "CLI=music-converter"
"%CLI%" skill install --target claude
if errorlevel 1 (
    echo Failed to install the Claude Code Skill.
    pause
    exit /b 1
)
echo Claude Code Skill installed.
timeout /t 2 >nul

