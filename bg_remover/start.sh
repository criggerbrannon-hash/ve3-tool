#!/bin/bash

echo ""
echo "======================================"
echo "    BG REMOVER PRO - Starting..."
echo "======================================"
echo ""

cd "$(dirname "$0")"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python3 not found!"
    echo "Please install Python3"
    exit 1
fi

# Create venv if needed
if [ ! -d "venv" ]; then
    echo "[INFO] Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Run the app
echo ""
echo "[INFO] Starting server..."
echo "[INFO] Opening browser at http://127.0.0.1:5000"
echo ""
python3 run.py
