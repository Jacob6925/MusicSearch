@echo off
rem Windows: run .\run.bat in PowerShell/CMD, or double-click it.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto :nosetup

".venv\Scripts\python.exe" app.py %*
set "RC=%errorlevel%"
if not "%RC%"=="0" if not defined MUSICSEARCH_CI pause
exit /b %RC%

:nosetup
echo.
echo MusicSearch is not set up yet. Run setup.bat first.
if not defined MUSICSEARCH_CI pause
exit /b 1
