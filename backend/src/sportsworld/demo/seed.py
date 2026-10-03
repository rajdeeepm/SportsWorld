from __future__ import annotations

import json
from pathlib import Path

from sportsworld.schemas import ContextSignal, EntityMetric, EntityProfile, EventCreate


def seed_context_memory(ctx, repo: Path) -> dict[str, int]:
    path = repo / "data" / "fixtures" / "context" / "context_demo.json"
    if not path.exists():
        return {"profiles": 0, "metrics": 0, "signals": 0}
    data = json.loads(path.read_text())
    profiles = [EntityProfile.model_validate(x) for x in data.get("profiles", [])]
    metrics = [EntityMetric.model_validate(x) for x in data.get("metrics", [])]
    signals = [ContextSignal.model_validate(x) for x in data.get("signals", [])]
    ctx.context_engine.seed(profiles, metrics, signals)
    return {"profiles": len(profiles), "metrics": len(metrics), "signals": len(signals)}


def seed_demo_events(ctx) -> list[str]:
    repo = Path(__file__).resolve().parents[4]
    # Historical memory is loaded before event creation so version-0 forecasts
    # begin with a genuine prior/context state rather than a raw scoreboard.
    seed_context_memory(ctx, repo)
    config = json.loads((repo / "data" / "fixtures" / "demo_events.json").read_text())
    created = []
    existing = {e.event_id for e in ctx.store.list_events()}
    for item in config:
        if item["event_id"] in existing:
            continue
        req = EventCreate.model_validate(item)
        ctx.engine.create_event(req, status="replay")
        created.append(req.event_id)
        replay_path = repo / "data" / "replays" / f"{req.event_id}.jsonl"
        if replay_path.exists():
            ctx.replay.load(req.event_id)
    return created


def main():
    from sportsworld.config import get_settings
    from sportsworld.api.context import build_context
    ctx = build_context(get_settings())
    print(seed_demo_events(ctx))
