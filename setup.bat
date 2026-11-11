@echo off
rem Windows: run .\setup.bat in PowerShell/CMD, or double-click it.
setlocal
cd /d "%~dp0"

set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if defined PY goto :found
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY goto :found

echo.
echo Python 3.10 or newer was not found.
echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH"
echo on the first installer screen, then close this window and run setup again.
if not defined MUSICSEARCH_CI pause
exit /b 1

:found
%PY% setup.py %*
set "RC=%errorlevel%"
if not defined MUSICSEARCH_CI pause
exit /b %RC%
