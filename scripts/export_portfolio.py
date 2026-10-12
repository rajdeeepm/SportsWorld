"""Build the static NFL exhibit, offline, from a content-addressed replay bundle.

First capture: --capture uses the local archived ESPN schedule and existing
preseason parameter artifact. Subsequent runs need only the committed bundle,
numpy, and the repository's engine. No provider, LLM, database, or API calls.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))

import numpy as np

from sportsworld.ingest.espn import GameRecord, read_archive
from sportsworld.ingest.ratings import RatingParams
from sportsworld.season.engine import (
    SeasonScenario, _played_tables, build_setup, run_season, simulate_regular,
)

PUBLIC = ROOT / "portfolio"
AS_OF = "2025-11-01T12:00:00+00:00"
SEED = 17
DRAWS = 10000
SCENARIOS = [
    ("stronger", "+3 points of strength", 3.0),
    ("weaker", "−3 points of strength", -3.0),
    ("win", "Win the next game", None),
    ("loss", "Lose the next game", None),
]


def stable_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def capture():
    games = [g for g in read_archive(ROOT / "data/real", "nfl") if g.start_time.year <= 2026]
    # Restrict to seasons relevant to the cutoff; no current 2026-season results.
    games = [g for g in games if g.season <= 2025]
    artifact = json.loads((ROOT / "data/fixtures/backtests/season_nfl_ext.json").read_text())
    param_row = next(r for r in artifact["rows"] if r["season"] == 2025 and r["checkpoint"] == 0 and r["mode"] == "dynamic")
    cohort = [r for r in artifact["rows"] if 2021 <= r["season"] <= 2025]
    return {
        "as_of": AS_OF,
        "season": 2025,
        "params": param_row["rating_params"],
        "parameter_source": "data/fixtures/backtests/season_nfl_ext.json: NFL 2025 preseason row; fitted to earlier seasons",
        "structure": json.loads((ROOT / "data/real/structure/nfl/2025.json").read_text()),
        "games": [g.model_dump(mode="json") for g in games],
        "research_rows": cohort,
        "research_source": "data/fixtures/backtests/season_nfl_ext.json; filtered NFL 2021–2025",
    }


def compact_team(t):
    # Do not ship the known-invalid Bernoulli seed summary or imply exact ties.
    keys = ["team_id", "name", "abbreviation", "conference", "division", "rating", "rating_sd", "games", "expected_wins", "wins_sd", "wins_p05", "wins_p95", "win_hist", "playoffs"]
    return {k: t[k] for k in keys if k in t}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--capture", action="store_true", help="Refresh bundled inputs from existing local archives, without network")
    ap.add_argument("--output", type=Path, default=PUBLIC / "snapshot.json")
    args = ap.parse_args()
    PUBLIC.mkdir(exist_ok=True)
    bundle_path = PUBLIC / "replay-inputs.b64"
    if args.capture:
        inputs = capture()
        bundle_path.write_text(base64.b64encode(gzip.compress(stable_bytes(inputs), mtime=0)).decode() + "\n")
    else:
        inputs = json.loads(gzip.decompress(base64.b64decode(bundle_path.read_text())))
    digest = hashlib.sha256(stable_bytes(inputs)).hexdigest()
    games = [GameRecord.model_validate(x) for x in inputs["games"]]
    cutoff = datetime.fromisoformat(inputs["as_of"])
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        struct = root / "structure/nfl/2025.json"
        struct.parent.mkdir(parents=True)
        struct.write_text(json.dumps(inputs["structure"]))
        setup = build_setup("nfl", root, cutoff, season=2025, params=RatingParams(**inputs["params"]), games=games)
        assert setup.T == 32 and setup.member.all() and not setup.postseason_started
        base = run_season(setup, draws=DRAWS, seed=SEED, mode="dynamic")
        fast = run_season(setup, draws=DRAWS, seed=SEED, mode="fast")
        played = _played_tables(setup)
        reg_base = simulate_regular(setup, DRAWS, np.random.default_rng(SEED), mode="dynamic")
        by_team = {t["team_id"]: compact_team(t) for t in base["teams"]}
        fast_by = {t["team_id"]: compact_team(t) for t in fast["teams"]}
        examples = {}
        schedule = []
        for i, eid in enumerate(setup.r_event_ids):
            schedule.append({"event_id": eid, "start": setup.r_start[i].isoformat(), "home_id": setup.team_ids[setup.r_home[i]], "away_id": setup.team_ids[setup.r_away[i]], "neutral": bool(setup.r_neutral[i])})
        for tid, t in by_team.items():
            i = setup.index()[tid]
            t["record"] = {k: int(played[k][i]) for k in ["wins", "losses", "ties"]}
            t["fast"] = fast_by[tid]
            next_game = next((g for g in schedule if tid in [g["home_id"], g["away_id"]]), None)
            t["next_game"] = next_game
            examples[tid] = {}
            for kind, label, delta in SCENARIOS:
                if delta is None and next_game is None:
                    continue
                if delta is None:
                    side = "home" if next_game["home_id"] == tid else "away"
                    if kind == "loss":
                        side = "away" if side == "home" else "home"
                    scenario = SeasonScenario(forced={next_game["event_id"]: side}, label=label)
                else:
                    scenario = SeasonScenario(rating_shifts=[(tid, delta, None, None)], label=label)
                alt = run_season(setup, draws=DRAWS, seed=SEED, mode="dynamic", scenario=scenario)
                alt_reg = simulate_regular(setup, DRAWS, np.random.default_rng(SEED), mode="dynamic", scenario=scenario)
                delta_wins = alt_reg.wins[:, i] - reg_base.wins[:, i]
                alt_by = {x["team_id"]: compact_team(x) for x in alt["teams"]}
                other = [{"team_id": x, "name": y["name"], "playoff_delta": round(alt_by[x]["playoffs"] - y["playoffs"], 4)} for x, y in by_team.items() if x != tid]
                other.sort(key=lambda x: -abs(x["playoff_delta"]))
                examples[tid][kind] = {"label": label, "team": alt_by[tid], "wins_delta": round(float(delta_wins.mean()), 4), "wins_delta_se": round(float(delta_wins.std(ddof=1) / np.sqrt(DRAWS)), 5), "other_teams": other[:5]}
            print(f"Saved four scenario branches for {t['name']}", flush=True)

    research = []
    for cp in [0.0, 0.25, 0.5, 0.75]:
        entry = {"checkpoint": cp}
        for mode in ["dynamic", "fast"]:
            rows = [r for r in inputs["research_rows"] if r["checkpoint"] == cp and r["mode"] == mode]
            assert len(rows) == 5 and len({r["season"] for r in rows}) == 5
            entry[mode] = {"coverage": float(np.mean([r["wins_90_coverage"] for r in rows])), "mae": float(np.mean([r["wins_mae"] for r in rows]))}
        research.append(entry)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    out = {
        "schema_version": 1, "title": "SportsWorld NFL historical exhibit", "as_of": inputs["as_of"], "season": 2025,
        "draws": DRAWS, "seed": SEED, "simulator": base["simulator_version"], "source_commit": sha,
        "input_sha256": digest, "parameter_source": inputs["parameter_source"], "params": inputs["params"],
        "regular_games": len(schedule) + len(setup.p_home), "played_games": len(setup.p_home),
        "teams": sorted(by_team.values(), key=lambda t: (-t["expected_wins"], t["name"])),
        "schedule": schedule, "scenarios": examples,
        "research": {"source": inputs["research_source"], "seasons": [2021, 2022, 2023, 2024, 2025], "team_seasons": 160, "rows": inputs["research_rows"], "summary": research},
        "limitations": [
            "Historical schedule and conference membership are retrospective snapshots; their publication times were not archived.",
            "Completed results enter the rating reconstruction at kickoff plus four hours, a proxy rather than an observed final-publication time.",
            "Season draws use Gaussian latent-strength margins, not the separately calibrated live game classifier.",
            "NFL future ties are not generated and official tiebreak chains are approximated. Playoff probabilities are conditional model outputs.",
            "Fixed-strength and correlated modes differ in uncertainty and drift, so this is not a perfectly matched-marginal correlation-only experiment.",
            "Research rows are existing archived evaluations. Wins coverage uses ±0.5 boundary tolerance; team-seasons share season outcomes and are not independent observations.",
            "Model form and fitted-parameter uncertainty are not fully represented. Monte Carlo precision is not predictive accuracy.",
            "Saved strength changes are hypothetical interventions, not estimated injury effects or causal player predictions.",
        ],
    }
    for t in out["teams"]:
        assert t["games"] == 17 and sum(t["win_hist"]) == DRAWS
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(stable_bytes(out))
    # A classic script also makes the exhibit inspectable by opening index.html
    # directly, without fetch/CORS or a development server.
    if args.output == PUBLIC / "snapshot.json":
        (PUBLIC / "snapshot-data.js").write_bytes(b"window.SPORTSWORLD_SNAPSHOT=" + stable_bytes(out) + b";\n")
    print(f"Wrote {args.output} ({args.output.stat().st_size:,} bytes); input SHA256 {digest}")


if __name__ == "__main__":
    main()
