#!/usr/bin/env bash
# Runs the BojAI backend API (FastAPI/uvicorn on :8000), waits for it to come
# up, then starts the frontend (Vite on :5173) and opens it in the browser.
# Ctrl+C stops both.
#
# Before starting, makes sure the local data folder exists (~/.bojai in the
# backend's home, with bojai.db, files/ and cache/; override with BOJAI_HOME=...).
#
# Override the interpreter with PYTHON=/path/to/python ./run_app_locally.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_URL="http://127.0.0.1:8000"
FRONTEND_PORT=5173

# Pick the first interpreter that has the backend's dependencies installed.
find_python() {
  local candidates=()
  [ -n "${PYTHON:-}" ] && candidates+=("$PYTHON")
  # Git Bash on Windows sets USERNAME but not USER; with `set -u` a bare $USER aborts.
  candidates+=(python python3 "$HOME/anaconda3/bin/python" "/mnt/c/Users/${USER:-${USERNAME:-}}/anaconda3/python.exe")
  for py in "${candidates[@]}"; do
    if command -v "$py" >/dev/null 2>&1 && "$py" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
      echo "$py"
      return 0
    fi
  done
  return 1
}

if ! PY="$(find_python)"; then
  echo "No Python with fastapi + uvicorn found. Install requirements.txt or set PYTHON=..." >&2
  exit 1
fi

# Under WSL with only a Windows Node install, the `npm` shell shim can't find
# `node`, so go through npm.cmd instead.
if command -v npm >/dev/null 2>&1 && command -v node >/dev/null 2>&1; then
  NPM=(npm)
elif command -v npm.cmd >/dev/null 2>&1 && command -v cmd.exe >/dev/null 2>&1; then
  NPM=(cmd.exe /c npm)
else
  echo "npm/node not found on PATH." >&2
  exit 1
fi

# Local data folder for persistence:
#   $BOJAI_HOME/bojai.db   SQLite database (created once, never overwritten)
#   $BOJAI_HOME/files/     uploaded/user files
#   $BOJAI_HOME/cache/     disposable cache
#
# "~" means the backend's home. For a Windows python.exe launched from WSL that
# is the Windows profile (C:\Users\<you>), not the WSL home: SQLite can't lock
# files on the \\wsl.localhost share, so a WSL-side db fails with "database is
# locked".
default_bojai_home() {
  if [[ "$PY" == *.exe ]] && command -v wslpath >/dev/null 2>&1; then
    local win_home
    win_home="$("$PY" -c "import pathlib; print(pathlib.Path.home())" | tr -d '\r')"
    [ -n "$win_home" ] || return 1
    echo "$(wslpath -u "$win_home")/.bojai"
  else
    echo "$HOME/.bojai"
  fi
}

if [ -z "${BOJAI_HOME:-}" ] && ! BOJAI_HOME="$(default_bojai_home)"; then
  echo "Could not determine the backend's home folder; set BOJAI_HOME=..." >&2
  exit 1
fi
BOJAI_DB="$BOJAI_HOME/bojai.db"
mkdir -p "$BOJAI_HOME/files" "$BOJAI_HOME/cache"

# A Windows python.exe (launched from WSL) needs Windows-style paths.
to_py_path() {
  if [[ "$PY" == *.exe ]] && command -v wslpath >/dev/null 2>&1; then
    wslpath -w "$1"
  else
    echo "$1"
  fi
}

if [ ! -f "$BOJAI_DB" ]; then
  echo "Creating SQLite database at $BOJAI_DB ..."
  # VACUUM writes the SQLite header, so the file is a real (empty) database
  # rather than a 0-byte placeholder.
  "$PY" -c "import sqlite3, sys; c = sqlite3.connect(sys.argv[1]); c.execute('VACUUM'); c.close()" \
    "$(to_py_path "$BOJAI_DB")"
fi
echo "Using data folder $BOJAI_HOME"

export BOJAI_HOME
if [[ "$PY" == *.exe ]]; then
  # Forward BOJAI_HOME to the Windows backend, translated to a Windows path.
  export WSLENV="${WSLENV:+$WSLENV:}BOJAI_HOME/p"
fi

cleanup() {
  # Runs once, from the EXIT trap (the signal traps below exit into it).
  [ -n "${CLEANED_UP:-}" ] && return
  CLEANED_UP=1
  if [ -n "${FRONTEND_PID:-}" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    echo "Stopping frontend..."
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
  # Killing cmd.exe from WSL doesn't reach the Windows node.exe it spawned, so
  # take down this script's `npm run dev` process tree on the Windows side.
  if [ "${NPM[0]}" = "cmd.exe" ]; then
    powershell.exe -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" | Where-Object { \$_.CommandLine -like '*npm-cli.js* run dev*--port $FRONTEND_PORT*' } | ForEach-Object { taskkill /T /F /PID \$_.ProcessId }" >/dev/null 2>&1 || true
  fi
  if [ -n "${BACKEND_PID:-}" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "Stopping backend..."
    kill "$BACKEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "Starting backend with $PY ..."
(cd "$SCRIPT_DIR" && "$PY" backend/app.py) &
BACKEND_PID=$!

# Poll with the same interpreter so the check runs in the server's own network
# namespace (matters when a Windows python.exe is launched from WSL).
echo "Waiting for backend at $BACKEND_URL ..."
for _ in $(seq 1 60); do
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "Backend exited during startup." >&2
    exit 1
  fi
  if "$PY" -c "import urllib.request; urllib.request.urlopen('$BACKEND_URL/docs', timeout=1)" >/dev/null 2>&1; then
    echo "Backend is up."
    break
  fi
  sleep 1
done

cd "$SCRIPT_DIR/frontend"
if [ ! -d node_modules ]; then
  echo "Installing frontend dependencies..."
  "${NPM[@]}" install
fi

echo "Starting frontend on http://localhost:$FRONTEND_PORT ..."
# --open makes Vite launch the default browser once the dev server is ready.
"${NPM[@]}" run dev -- --port "$FRONTEND_PORT" --strictPort --open &
FRONTEND_PID=$!
wait "$FRONTEND_PID"
