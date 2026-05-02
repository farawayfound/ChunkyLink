@echo off
echo ========================================
echo vpoRAG MCP Dashboard Launcher
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
echo Starting MCP Dashboard at http://localhost:5001
echo.
python local\run.py

pause
