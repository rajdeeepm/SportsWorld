#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT/backend/src"
export SPORTSWORLD_ENV="${SPORTSWORLD_ENV:-demo}"
exec uvicorn sportsworld.api.main:app --host 0.0.0.0 --port "${PORT:-8000}" --reload
