"""Reproduce cloud inputs and one full refresh offline; never read credentials."""
import asyncio
import gc
import importlib.util
import json
import os
from pathlib import Path
import resource
import sys
import time

root = Path(__file__).resolve().parents[1]
scratch = Path(sys.argv[1] if len(sys.argv) > 1 else "/private/tmp/sportsworld-memory-profile")
scratch.mkdir(parents=True, exist_ok=True)
(scratch / "deployment").mkdir(exist_ok=True)
link = scratch / "deployment" / "engine-data"
if not link.exists():
    link.symlink_to(root / "deployment" / "engine-data", target_is_directory=True)
spec = importlib.util.spec_from_file_location("cloud_inputs", root / "scripts/prepare_cloud_data.py")
inputs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inputs)
inputs.prepare(scratch)

from sportsworld.api.context import build_context
from sportsworld.config import Settings
from sportsworld.ingest.tracker import TrackerService
from sportsworld.resource_usage import memory_sample
from sportsworld.season.service import SeasonService
from sportsworld.season.engine import SeasonScenario

records = []
def record(phase):
    row = {"phase": phase, **memory_sample()}
    records.append(row)
    print(json.dumps(row), flush=True)
    (scratch / "profile.json").write_text(json.dumps(records, indent=2))

async def main():
    settings = Settings(_env_file=None, sportsworld_env="production", llm_api_key=None,
                        elevenlabs_api_key=None, spacetimedb_url=None, database_url=None,
                        model_dir=root / "models/artifacts", manifest_dir=root / "models/manifests",
                        backtest_dir=root / "data/fixtures/backtests")
    ctx = build_context(settings)
    record("context")
    leagues = ["nfl", "college-football", "nba", "mens-college-basketball", "nhl", "mens-college-hockey", "f1"]
    tracker = TrackerService(ctx, scratch / "data/real", leagues)
    tracker.build()
    record("seven-trackers")
    svc = SeasonService(scratch / "data/real", ctx.registry, trackers=tracker.trackers)
    active = [league for league in leagues if league != "mens-college-hockey"]
    for league in active:
        svc._load_warm(league)
    record("all-warm-states")
    requested = [arg for arg in sys.argv[2:] if arg != "--scenario"] or active
    for league in requested:
        before = time.monotonic()
        svc.compute(league)
        record(f"compute:{league}:{time.monotonic()-before:.2f}s")
        if "--scenario" in sys.argv and league != "f1":
            team = svc.state(league).run["teams"][0]["team_id"]
            before = time.monotonic()
            svc.scenario(league, SeasonScenario(rating_shifts=[(team, 3.0, None, None)], label="memory profile"))
            record(f"scenario:{league}:{time.monotonic()-before:.2f}s")
        gc.collect()
    await tracker.stop()

asyncio.run(main())
