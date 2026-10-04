#!/usr/bin/env bash
# Keep an SSH tunnel to the self-hosted Llama (vLLM) open on localhost:8001, reconnecting whenever it drops.
# Host comes from LLM_TUNNEL_HOST in .env (not committed).
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${LLM_TUNNEL_HOST:-$(grep -E '^LLM_TUNNEL_HOST=' "$ROOT/.env" | tail -1 | cut -d= -f2-)}"
[ -n "$HOST" ] || { echo "set LLM_TUNNEL_HOST in .env"; exit 1; }
while true; do
  if ! curl -s -m 3 -o /dev/null http://127.0.0.1:8001/v1/models; then
    echo "$(date '+%H:%M:%S') opening Llama tunnel"
    ssh -o BatchMode=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes \
        -o ConnectTimeout=10 -N -L 8001:127.0.0.1:8001 "$HOST"
    echo "$(date '+%H:%M:%S') tunnel closed; retrying in 5 s"
  fi
  sleep 5
done
