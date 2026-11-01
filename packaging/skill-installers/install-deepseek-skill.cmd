@echo off
setlocal
set "CLI=%LOCALAPPDATA%\Programs\ShaoLv\music-converter.exe"
if not exist "%CLI%" set "CLI=music-converter"
"%CLI%" skill install --target deepseek
if errorlevel 1 (
    echo Failed to install the DeepSeek Harness Skill.
    pause
    exit /b 1
)
echo DeepSeek Harness Skill installed.
timeout /t 2 >nul

