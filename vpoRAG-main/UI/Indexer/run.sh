#!/bin/bash

echo "========================================"
echo "vpoRAG Control Panel Launcher"
echo "========================================"
echo ""

cd "$(dirname "$0")"

echo "Checking dependencies..."
if ! pip show flask > /dev/null 2>&1; then
    echo "Installing dependencies..."
    pip install -r requirements.txt
fi

echo ""
echo "Starting UI server..."
echo ""
python app.py
