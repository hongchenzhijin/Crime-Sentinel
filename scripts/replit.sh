#!/usr/bin/env bash
# Replit build/start for Crime Sentinel: FastAPI serves both /api and the built dashboard on port 8000.
#   bash scripts/replit.sh build   # install deps, build the frontend, load the demo dataset
#   bash scripts/replit.sh start   # run the server
set -euo pipefail
cd "$(dirname "$0")/.."

case "${1:-}" in
  build)
    pip install -r backend/requirements.txt
    (cd frontend && npm ci && npm run build)
    # Load the committed synthetic dataset (deterministic; no regeneration).
    python scripts/load_demo_data.py --no-generate
    ;;
  start)
    # The DB resets on redeploy/restart; reload it if it is missing.
    [ -f backend/crime_sentinel.db ] || python scripts/load_demo_data.py --no-generate
    cd backend
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000
    ;;
  *)
    echo "usage: $0 build|start" >&2
    exit 1
    ;;
esac
