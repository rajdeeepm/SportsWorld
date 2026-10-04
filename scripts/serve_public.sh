#!/usr/bin/env bash
# Serve SportsWorld publicly at https://worldofsports.tech through a Cloudflare Tunnel from this machine.
#   API (engine)        127.0.0.1:8000  <- /api on the same origin
#   Site (vite preview) 127.0.0.1:4173  <- https://worldofsports.tech
#   Live world state    SpacetimeDB Maincloud (browsers connect directly)
#   Fetch.ai agent      127.0.0.1:8020 (Agentverse mailbox, ASI:One)
#   Llama (chat prose)  127.0.0.1:8001 via scripts/llm_tunnel.sh (optional; answers work without it)
# Keeps the machine awake while it runs. Stop with Ctrl-C.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${PYTHON:-$ROOT/../env/bin/python}"
mkdir -p logs

echo "building the site…"
(cd frontend && npm run build >/dev/null)

if ! curl -s -o /dev/null http://127.0.0.1:8000/health; then
  echo "starting the API…"
  PYTHONPATH=backend/src SPORTSWORLD_ENV=demo TRACKER_ENABLED=true nohup "$PY" -m uvicorn sportsworld.api.main:app --host 127.0.0.1 --port 8000 > logs/api.log 2>&1 &
fi

if ! lsof -ti tcp:8020 >/dev/null 2>&1; then
  echo "starting the Fetch.ai agent…"
  (cd agents/sportsworld_analyst && nohup "$PY" agent.py > ../../logs/agent.log 2>&1 &)
fi

if ! lsof -ti tcp:8001 >/dev/null 2>&1 && grep -q '^LLM_TUNNEL_HOST=' .env 2>/dev/null; then
  echo "opening the Llama tunnel…"
  nohup scripts/llm_tunnel.sh > logs/llm_tunnel.log 2>&1 &
fi

if lsof -ti tcp:4173 >/dev/null 2>&1; then
  echo "restarting the site on :4173 with the new build…"
  lsof -ti tcp:4173 | xargs kill 2>/dev/null || true
  sleep 1
fi
echo "starting the site on :4173…"
(cd frontend && nohup npx vite preview > ../logs/site.log 2>&1 &)

echo "opening the tunnel (worldofsports.tech)…"
exec caffeinate -dimsu cloudflared tunnel --config "$HOME/.cloudflared/sportsworld.yml" run sportsworld
