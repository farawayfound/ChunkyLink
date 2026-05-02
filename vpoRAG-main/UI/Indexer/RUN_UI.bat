@echo off
echo ========================================
echo vpoRAG Control Panel Launcher
echo ========================================
echo.

cd /d "%~dp0"

echo Checking dependencies...
pip show flask >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r requirements.txt
)

echo.
echo Starting UI server...
echo.
python app.py

pause
