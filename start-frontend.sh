#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

# Frontend startup script for local development

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm ci
fi

echo "Starting DataSays UI on http://127.0.0.1:5173"

exec npm run dev
