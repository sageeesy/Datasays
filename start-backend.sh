#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/server"

# Check if .env exists
if [ ! -f .env ]; then
    echo ".env was not found; creating it from env.example."
    cp env.example .env
    echo "Set OPENROUTER_API_KEY in server/.env, then run this script again."
    exit 1
fi

PYTHON_BIN="python3"
if [ -x "venv/bin/python" ] && venv/bin/python -c "import fastapi, uvicorn" >/dev/null 2>&1; then
    PYTHON_BIN="venv/bin/python"
fi

if ! "$PYTHON_BIN" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
    echo "Installing backend dependencies..."
    "$PYTHON_BIN" -m pip install -r requirements.txt
fi

echo "Starting DataSays API on http://127.0.0.1:8000"
echo "API docs: http://127.0.0.1:8000/docs"

exec "$PYTHON_BIN" -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
