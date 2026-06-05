#!/bin/bash
echo ""
echo "================================"
echo "  SHLOKA — Starting App"
echo "================================"
echo ""

# Find python3 or python
if command -v python3 &>/dev/null; then
    PY=python3
    PIP=pip3
elif command -v python &>/dev/null; then
    PY=python
    PIP=pip
else
    echo "ERROR: Python not found."
    echo "Download from: https://www.python.org/downloads/"
    exit 1
fi

echo "Python: $($PY --version)"
echo ""

# Install packages if missing
$PY -c "import flask" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Installing packages..."
    $PIP install flask flask-sqlalchemy flask-login werkzeug python-slugify
    echo ""
fi

echo "Open browser at: http://localhost:5000"
echo "Press CTRL+C to stop"
echo ""
$PY run.py
