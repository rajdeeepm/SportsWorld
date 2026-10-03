#!/usr/bin/env bash
# Serve SportsWorld publicly at https://sportsworld.tech through a Cloudflare Tunnel from this machine.
#   API (engine)        127.0.0.1:8000  <- /api on the same origin
#   Site (vite preview) 127.0.0.1:4173  <- https://sportsworld.tech
#   Live world state    SpacetimeDB Maincloud (browsers connect directly)
# Keeps the machine awake while it runs. Stop with Ctrl-C.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${PYTHON:-../env/bin/python}"
mkdir -p logs

echo "building the site…"
(cd frontend && npm run build >/dev/null)

if ! curl -s -o /dev/null http://127.0.0.1:8000/health; then
  echo "starting the API…"
  PYTHONPATH=backend/src SPORTSWORLD_ENV=demo TRACKER_ENABLED=true nohup "$PY" -m uvicorn sportsworld.api.main:app --host 127.0.0.1 --port 8000 > logs/api.log 2>&1 &
fi

echo "starting the site on :4173…"
(cd frontend && nohup npx vite preview > ../logs/site.log 2>&1 &)

echo "opening the tunnel (sportsworld.tech)…"
exec caffeinate -dimsu cloudflared tunnel --config "$HOME/.cloudflared/sportsworld.yml" run sportsworld
