@echo off
setlocal EnableExtensions
title ShaoLv Launcher
set "APP_ROOT=%~dp0"
cd /d "%APP_ROOT%"
set "PYTHON=%APP_ROOT%.venv\Scripts\python.exe"
set "LAUNCHER=%APP_ROOT%launcher.py"

if not exist "%PYTHON%" goto missing_environment
if not exist "%LAUNCHER%" goto missing_launcher

echo Starting ShaoLv Music Converter...
"%PYTHON%" "%LAUNCHER%"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" goto startup_failed
exit /b 0

:missing_environment
echo Virtual environment not found. Run setup.ps1 first.
pause
exit /b 2

:missing_launcher
echo launcher.py not found. The project files may be incomplete.
pause
exit /b 2

:startup_failed
echo.
echo Startup failed. See .music-converter-data\logs\launcher.log
pause
exit /b %EXIT_CODE%


