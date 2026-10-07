#!/usr/bin/env bash
# Runs the BojAI backend (FastAPI/uvicorn) and frontend (Vite) together.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

read -rsp "Enter your OpenAI API key: " OPENAI_API_KEY
echo
export OPENAI_API_KEY

if [ -z "$OPENAI_API_KEY" ]; then
  echo "No API key entered, exiting." >&2
  exit 1
fi

cleanup() {
  if [ -n "${BACKEND_PID:-}" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null
    wait "$BACKEND_PID" 2>/dev/null
  fi
}
trap cleanup EXIT INT TERM

echo "Starting backend..."
(python backend/app.py) &
BACKEND_PID=$!

echo "Starting frontend..."
(cd "$SCRIPT_DIR/frontend" && npm run dev)
