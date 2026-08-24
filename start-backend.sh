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

PYTHON_BIN=""
PYTHON_CANDIDATES=(
    "${DATASAYS_PYTHON:-}"
    "venv/bin/python"
    "$(command -v python3 2>/dev/null || true)"
    "/opt/anaconda3/envs/datasays/bin/python"
    "$HOME/anaconda3/envs/datasays/bin/python"
    "$HOME/miniconda3/envs/datasays/bin/python"
)

for candidate in "${PYTHON_CANDIDATES[@]}"; do
    if [ -n "$candidate" ] && [ -x "$candidate" ] && "$candidate" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
        PYTHON_BIN="$candidate"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    PYTHON_BIN="$(command -v python3 2>/dev/null || true)"
fi

if [ -z "$PYTHON_BIN" ]; then
    echo "Python 3 was not found. Install Python 3.11+ and run this script again."
    exit 1
fi

if ! "$PYTHON_BIN" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
    echo "Installing backend dependencies..."
    "$PYTHON_BIN" -m pip install -r requirements.txt
fi

echo "Starting DataSays API on http://127.0.0.1:8000"
echo "API docs: http://127.0.0.1:8000/docs"

exec "$PYTHON_BIN" -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
