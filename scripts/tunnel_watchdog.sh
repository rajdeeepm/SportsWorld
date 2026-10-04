#!/usr/bin/env bash
# Keep worldofsports.tech reachable: if the public site fails twice in a row, restart the Cloudflare Tunnel.
cd "$(dirname "$0")/.." || exit 1
fails=0
while true; do
  code=$(curl -s -m 15 -o /dev/null -w "%{http_code}" https://www.worldofsports.tech/college-football)
  if [ "$code" = "200" ]; then fails=0; else fails=$((fails + 1)); echo "$(date '+%H:%M:%S') public site returned $code (fail $fails)"; fi
  if [ "$fails" -ge 2 ]; then
    echo "$(date '+%H:%M:%S') restarting tunnel"
    pkill -f "cloudflared tunnel"; sleep 2
    nohup caffeinate -dimsu cloudflared tunnel --protocol http2 --config "$HOME/.cloudflared/sportsworld.yml" run sportsworld >> logs/tunnel.log 2>&1 &
    fails=0; sleep 30
  fi
  sleep 60
done
