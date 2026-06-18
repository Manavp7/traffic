#!/usr/bin/env bash
# One-command dev demo: seed -> history -> train -> API + dashboard (no Docker/GPU).
set -euo pipefail
cd "$(dirname "$0")/.."

VENV="${VENV:-.venv}"
PY="$VENV/bin/python"

echo "==> Seeding road network + history"
"$PY" -m traffic_os.cli seed
"$PY" -m traffic_os.cli history --days 7

echo "==> Starting API (http://localhost:8000) — trains models in background"
"$VENV/bin/uvicorn" traffic_os.api.app:app --host 0.0.0.0 --port 8000 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true' EXIT

echo "==> Starting dashboard (http://localhost:5173)"
cd dashboard
[ -d node_modules ] || npm install
VITE_API_URL="${VITE_API_URL:-http://localhost:8000}" npm run dev
