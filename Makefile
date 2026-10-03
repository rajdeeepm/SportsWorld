.PHONY: test demo backend frontend train data smoke docker real-data train-real live replay-demo

data:
	python scripts/generate_demo_data.py

train: data
	PYTHONPATH=backend/src python scripts/train_demo.py

test:
	cd backend && PYTHONPATH=src pytest

smoke:
	PYTHONPATH=backend/src SPORTSWORLD_ENV=demo python scripts/smoke_test.py

backend:
	PYTHONPATH=backend/src SPORTSWORLD_ENV=demo uvicorn sportsworld.api.main:app --host 0.0.0.0 --port 8000 --reload

frontend:
	cd frontend && npm install && npm run dev

demo:
	./scripts/run_demo.sh

docker:
	docker compose up --build

# --- Real data: every team, every game -------------------------------------
real-data:
	PYTHONPATH=backend/src python scripts/backfill_espn.py
	PYTHONPATH=backend/src python scripts/backfill_pbp.py
	PYTHONPATH=backend/src python scripts/backfill_f1.py

train-real:
	PYTHONPATH=backend/src python scripts/train_real.py

live:
	PYTHONPATH=backend/src SPORTSWORLD_ENV=demo TRACKER_ENABLED=true uvicorn sportsworld.api.main:app --host 0.0.0.0 --port 8000

# Offline, no-network judge demo: every competition rebuilt exactly as it stood at a past instant
replay-demo:
	PYTHONPATH=backend/src SPORTSWORLD_ENV=demo TRACKER_ENABLED=false SEASON_AS_OF=$${AS_OF:-2025-12-01T00:00:00Z} uvicorn sportsworld.api.main:app --host 0.0.0.0 --port 8000

# Live shared world state (SpacetimeDB). Starts a local server on :3010 and publishes infra/spacetimedb.
# The API publishes into it when SPACETIMEDB_URL / SPACETIMEDB_TOKEN are set in .env.
spacetime:
	@command -v spacetime >/dev/null || { echo "install: curl -sSf https://install.spacetimedb.com | sh"; exit 1; }
	@(curl -s -o /dev/null http://127.0.0.1:3010/v1/ping && echo "SpacetimeDB already running on :3010") || (nohup spacetime start --listen-addr 127.0.0.1:3010 > logs/spacetimedb.log 2>&1 & sleep 4)
	@spacetime server add sw-local --url http://127.0.0.1:3010 --no-fingerprint >/dev/null 2>&1 || true
	cd infra/spacetimedb && npm install --silent && spacetime publish sportsworld --server sw-local --yes
	spacetime generate --lang typescript --out-dir frontend/src/stdb --module-path infra/spacetimedb
