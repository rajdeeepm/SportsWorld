"""Competition-season API (spec v3.0 §21.1, Appendix E)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from sportsworld.ingest.leagues import LEAGUES
from sportsworld.season.engine import SeasonScenario, _played_tables, build_setup
from sportsworld.season.rules import RULES_VERSIONS

router = APIRouter(tags=["competitions"])
_service = None  # set by api.main at startup
_limiter_dep = None


def bind(service, limiter_dependency) -> None:
    global _service, _limiter_dep
    _service = service
    _limiter_dep = limiter_dependency


_archive = None


def bind_archive(archive) -> None:
    global _archive
    _archive = archive


def _svc():
    if _service is None:
        raise HTTPException(503, "season service not running (start the API with TRACKER_ENABLED=true or SEASON_ENGINE=true)")
    return _service


def _league(cid: str):
    if cid not in LEAGUES:
        raise HTTPException(404, "unknown competition")
    return LEAGUES[cid]


def _repo() -> Path:
    return Path(__file__).resolve().parents[4]


def _clean(x):
    """Replace NaN/inf (valid in Python's json, invalid in browsers) with None, recursively."""
    import math as _m
    if isinstance(x, float):
        return None if not _m.isfinite(x) else x
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_clean(v) for v in x]
    return x


@router.get("/competitions")
def competitions():
    svc = _service
    out = []
    for cid, spec in LEAGUES.items():
        st = svc.states.get(cid) if svc else None
        run = st.run if st else None
        out.append({"competition_id": cid, "name": spec.display_name, "sport_family": spec.sport.value,
                    "rules_version": RULES_VERSIONS.get(cid, "f1_rules_2026_v1" if cid == "f1" else None),
                    "season_engine": bool(st), "global_state_version": st.global_state_version if st else None,
                    "season_run_id": run.get("run_id") if run else None, "stale": bool(st and st.dirty)})
    return out


@router.get("/competitions/{cid}/seasons/current")
def season_summary(cid: str):
    _league(cid)
    st = _svc().state(cid)
    run = st.run or {}
    return {"competition_id": cid, "season": run.get("season"), "global_state_version": st.global_state_version, "run_id": run.get("run_id"),
            "as_of": run.get("as_of"), "status": "recomputing" if st.computing else ("stale" if st.dirty else "fresh"), "last_error": st.last_error,
            "rules_version": run.get("diagnostics", {}).get("rules_version") or run.get("rules_version"), "diagnostics": run.get("diagnostics"),
            "board_events": len(st.board)}


@router.get("/competitions/{cid}/seasons/current/forecast-board")
def forecast_board(cid: str, team: str | None = None, start: str | None = None, end: str | None = None, limit: int = 2000):
    _league(cid)
    st = _svc().state(cid)
    rows = sorted(st.board.values(), key=lambda r: r["start_time"])
    if team:
        rows = [r for r in rows if team in (r["home_id"], r["away_id"])]
    if start:
        rows = [r for r in rows if r["start_time"] >= start]
    if end:
        rows = [r for r in rows if r["start_time"] <= end]
    out = _with_live(cid, rows[:limit])
    return {"competition_id": cid, "global_state_version": st.global_state_version, "count": len(rows), "events": out}


def _with_live(cid: str, rows: list[dict]) -> list[dict]:
    """Overlay the tracker's latest game state; scores and clocks move between season recomputes."""
    tracker = _svc().trackers.get(cid)
    live = {g.event_id: g for g in getattr(tracker, "games", {}).values()}
    out = []
    for r in rows:
        g = live.get(r["event_id"])
        if g is not None:
            r = {**r, "state": g.state, "status": g.status_name, "period": g.period, "clock_seconds": g.clock_seconds,
                 "home_score": g.home.score, "away_score": g.away.score, "home_rank": g.home.rank, "away_rank": g.away.rank,
                 "home_record": g.home.record, "away_record": g.away.record, "venue": g.venue,
                 "conference_game": g.conference_game, "weather": g.weather or None}
        out.append(r)
    return out


@router.get("/competitions/{cid}/teams/meta")
def teams_meta(cid: str):
    """Official team identity (colours, logos) from ESPN; identity only, never a model input."""
    _league(cid)
    from sportsworld.ingest.team_meta import league_meta
    return league_meta(cid, _svc().data_root)


@router.get("/competitions/{cid}/seasons/current/season-forecast")
def season_forecast(cid: str, mode: str = "dynamic"):
    _league(cid)
    st = _svc().state(cid)
    run = st.run if mode == "dynamic" else st.fast_run
    if run is None:
        raise HTTPException(404, "no season run yet")
    return {**{k: v for k, v in run.items() if k != "games"}, "status": "stale" if st.dirty else "fresh"}


@router.get("/competitions/{cid}/seasons/current/updates")
def world_updates(cid: str):
    _league(cid)
    st = _svc().state(cid)
    return list(st.feed)


@router.get("/competitions/{cid}/seasons/current/standings")
def standings(cid: str):
    spec = _league(cid)
    if cid == "f1":
        run = _svc().state("f1").run or {}
        return {"competition_id": cid, "drivers": [{k: d[k] for k in ("code", "name", "constructor_id", "points_now", "wins_now")} for d in run.get("drivers", [])],
                "constructors": [{k: c[k] for k in ("name", "points_now")} for c in run.get("constructors", [])]}
    svc = _svc()
    setup = build_setup(cid, svc.data_root, datetime.now(timezone.utc), games=svc._games(cid), book=svc._book(cid))
    base = _played_tables(setup)
    official = {o.team_id: o for o in (setup.structure.official if setup.structure else [])}
    rows, mismatches = [], 0
    for i, tid in enumerate(setup.team_ids):
        if not setup.member[i]:
            continue
        w, l, t, otl = int(base["wins"][i]), int(base["losses"][i]), int(base["ties"][i]), int(base["otl"][i])
        off = official.get(tid)
        match = None
        if off is not None and setup.structure and setup.structure.espn_season == setup.espn_season:
            match = (off.wins, off.losses) == (w, l + (otl if spec.sport.value != "hockey" else 0))
            mismatches += int(match is False)
        rows.append({"team_id": tid, "name": setup.names[i], "abbreviation": setup.abbreviations[i],
                     "conference": setup.conf_names[setup.conf[i]] if setup.conf[i] >= 0 else None,
                     "division": setup.div_names[setup.div[i]] if setup.div[i] >= 0 else None,
                     "wins": w, "losses": l, "ties": t, "ot_losses": otl, "games": int(base["games"][i]),
                     "conf_record": f"{int(base['conf_w'][i])}-{int(base['conf_g'][i] - base['conf_w'][i])}",
                     "point_diff": round(float(base["pd"][i]), 1), "points": 2 * w + otl if spec.sport.value == "hockey" else None,
                     "official_matches": match})
    rows.sort(key=lambda r: ((r["points"] if r["points"] is not None else r["wins"] - r["losses"]), r["point_diff"]), reverse=True)
    return {"competition_id": cid, "as_of": datetime.now(timezone.utc).isoformat(), "rows": rows,
            "audit": {"official_source": "ESPN standings", "mismatches": mismatches, "teams": len(rows), "structure_note": setup.structure_note}}


@router.get("/competitions/{cid}/seasons/current/coverage")
def coverage(cid: str):
    """Schedule + forecast coverage audit (spec §7.1, G1/G2)."""
    _league(cid)
    svc = _svc()
    if cid == "f1":
        run = svc.state("f1").run or {}
        return {"competition_id": cid, "remaining_races": len(run.get("remaining_races", [])), "forecasted": len(run.get("remaining_races", []))}
    setup = build_setup(cid, svc.data_root, datetime.now(timezone.utc), games=svc._games(cid), book=svc._book(cid))
    st = svc.state(cid)
    ids = setup.r_event_ids
    missing = [e for e in ids if e not in st.board or st.board[e]["p_home"] is None]
    return {"competition_id": cid, "season": setup.season, "played_regular_season": int(len(setup.p_home)), "remaining_regular_season": len(ids),
            "duplicates": len(ids) - len(set(ids)), "contingent_postseason_events": setup.contingent_events,
            "board_events": len(st.board), "remaining_without_forecast": len(missing), "coverage": 1.0 - len(missing) / max(1, len(ids)),
            "stale_forecasts": sum(1 for r in st.board.values() if r["freshness"] != "fresh")}


class ShiftIn(BaseModel):
    target_id: str = Field(description="team_id, or for F1 a driver_id / constructor_id")
    delta: float = Field(description="rating change in the league's rating units (points / goals; F1 finishing-score units)")
    start: datetime | None = None
    end: datetime | None = None


class SeasonScenarioIn(BaseModel):
    label: str | None = None
    rating_shifts: list[ShiftIn] = Field(default_factory=list)
    forced_results: dict[str, str] = Field(default_factory=dict, description="event_id -> 'home'|'away'")
    draws: int = Field(default=10_000, ge=500, le=50_000)
    seed: int = 7


@router.post("/competitions/{cid}/seasons/current/season-simulations")
def season_simulation(cid: str, body: SeasonScenarioIn):
    _league(cid)
    scen = SeasonScenario(rating_shifts=[(s.target_id, s.delta, s.start, s.end) for s in body.rating_shifts], forced=body.forced_results, label=body.label)
    try:
        res = _svc().scenario(cid, scen, draws=body.draws, seed=body.seed)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    base, alt = res["base"], res["scenario"]
    strip = lambda r: {k: v for k, v in r.items() if k != "games"}  # noqa: E731
    return {"label": body.label, "base": strip(base), "scenario": strip(alt), "deltas": res["deltas"][:40],
            "note": "Branch-only simulation with common random numbers; canonical state and evidence unchanged."}


@router.get("/competitions/{cid}/backtests/season")
def season_backtest(cid: str):
    p = _repo() / "data" / "fixtures" / "backtests" / f"season_{cid}.json"
    if not p.exists():
        raise HTTPException(404, "no season backtest for this competition; run scripts/season_backtest.py")
    return _clean(json.loads(p.read_text()))


@router.get("/research/season-summary")
def season_summary_all():
    root = _repo() / "data" / "fixtures" / "backtests"
    ext = json.loads((root / "season_summary_ext.json").read_text())["summary"] if (root / "season_summary_ext.json").exists() else []
    base = json.loads((root / "season_summary.json").read_text())["summary"] if (root / "season_summary.json").exists() else []
    have = {r["league"] for r in ext}  # prefer the 7-season replay where it exists
    return _clean({"summary": ext + [r for r in base if r["league"] not in have]})


@router.get("/entities/team/{cid}/{team_id}")
def team_page(cid: str, team_id: str) -> dict[str, Any]:
    """Team season page payload: latent state, season distribution, remaining schedule with forecasts, rating history."""
    _league(cid)
    svc = _svc()
    st = svc.state(cid)
    run = st.run or {}
    row = next((t for t in run.get("teams", []) if t["team_id"] == team_id), None)
    if row is None:
        raise HTTPException(404, "team not in season run")
    sched = _with_live(cid, [r for r in sorted(st.board.values(), key=lambda r: r["start_time"]) if team_id in (r["home_id"], r["away_id"])])
    for r in sched:
        home = r["home_id"] == team_id
        r = r
    games = svc._games(cid)
    played = [g for g in games if g.completed and team_id in (g.home.team_id, g.away.team_id) and g.season_type in (2, 3)]
    played = sorted(played, key=lambda g: g.start_time)[-12:]
    book = svc._book(cid)
    history = []
    if book is not None and team_id in book.teams:
        history = book.teams[team_id].history[-40:]
    return {"team": row, "remaining": [{**r, "is_home": r["home_id"] == team_id,
                                        "p_win": r["p_home"] if r["home_id"] == team_id else (1 - r["p_home"] if r["p_home"] is not None else None)} for r in sched],
            "recent_results": [{"event_id": g.event_id, "date": g.start_time.isoformat(), "home": g.home.name, "away": g.away.name,
                                "home_score": g.home.score, "away_score": g.away.score} for g in played],
            "rating_history": [{"date": d, "rating": m, "var": v} for d, m, v in history],
            "meta": _team_detail(cid, team_id),
            "season_run_id": run.get("run_id"), "global_state_version": st.global_state_version}


def _team_detail(cid: str, team_id: str) -> dict[str, Any]:
    from sportsworld.ingest.team_meta import team_detail
    try:
        return team_detail(cid, team_id, _svc().data_root)
    except Exception:
        return {}


class AskIn(BaseModel):
    text: str = Field(min_length=3, max_length=500)
    run: bool = True
    draws: int = Field(default=10_000, ge=500, le=50_000)


@router.post("/competitions/{cid}/seasons/current/scenario/ask")
def ask_scenario(cid: str, body: AskIn):
    """Natural language -> typed season scenario (Llama structure + learned effect sizes) -> branch simulation."""
    from sportsworld.config import get_settings
    from sportsworld.llm.client import LLMClient
    from sportsworld.llm.season_scenario import parse_season_scenario
    _league(cid)
    svc = _svc()
    run = svc.state(cid).run or {}
    teams = run.get("teams") or [{"team_id": d["constructor_id"], "name": d["name"], "abbreviation": None} for d in run.get("constructors", [])]
    parsed = parse_season_scenario(body.text, cid, teams, LLMClient(get_settings()))
    out = {k: v for k, v in parsed.items() if k != "scenario"}
    if body.run and parsed["scenario"] is not None:
        res = svc.scenario(cid, parsed["scenario"], draws=body.draws)
        out["deltas"] = res["deltas"][:25]
        strip = lambda r: {k: v for k, v in r.items() if k != "games"}  # noqa: E731
        out["base"], out["scenario"] = strip(res["base"]), strip(res["scenario"])
        out["note"] = "Branch-only simulation with common random numbers; canonical state and evidence unchanged."
    return out


@router.get("/research/bakeoffs")
def research_bakeoffs():
    """Win-probability model bake-offs (real data) with game-clustered paired bootstrap CIs."""
    root = _repo() / "data" / "fixtures" / "backtests"
    out = []
    for p in sorted(root.glob("bakeoff_*.json")) + sorted(root.glob("pbp_bakeoff_*.json")):
        d = json.loads(p.read_text())
        out.append({"file": p.name, "league": d.get("league"), "kind": "football_play" if p.name.startswith("bakeoff_") else "pbp",
                    "rows": d.get("rows"), "test": d.get("test"), "data_fingerprint": d.get("data_fingerprint"),
                    "models": {k: {m: v.get(m) for m in ("log_loss", "brier", "ece", "accuracy", "temperature")} | ({"same_plays_as_espn": v["same_plays_as_espn"]} if "same_plays_as_espn" in v else {}) | ({"in_game_only": v["in_game_only"]} if "in_game_only" in v else {})
                               for k, v in d.get("models", {}).items()},
                    "paired_game_bootstrap": d.get("paired_game_bootstrap", {})})
    return _clean(out)


@router.get("/research/player-impact")
def research_player_impact():
    root = _repo() / "models" / "artifacts" / "player_impact"
    out = []
    for p in sorted(root.glob("*.json")):
        d = json.loads(p.read_text())
        out.append({k: d.get(k) for k in ("league", "model_version", "n_games", "residual_sd", "variance_explained", "by_position", "definition", "fit_window")})
    return out


@router.get("/research/consensus")
def research_consensus():
    """External market consensus vs SportsWorld on identical holdout games (benchmark only, never a feature)."""
    root = _repo() / "data" / "fixtures" / "backtests"
    out = []
    for p in sorted(root.glob("consensus_*.json")):
        d = json.loads(p.read_text())
        out.append({k: d.get(k) for k in ("league", "seasons", "status", "matched_games", "holdout_start", "interpretation", "model_version", "metrics")})
    return _clean(out)


@router.get("/research/rolling")
def research_rolling():
    root = _repo() / "data" / "fixtures" / "backtests"
    return _clean([json.loads(p.read_text()) for p in sorted(root.glob("rolling_*.json"))])


@router.get("/games/{cid}/{game_id}/view")
def live_game_view(cid: str, game_id: str):
    """Real ball / shot / event positions for one game plus SportsWorld's own win-probability history."""
    _league(cid)
    from sportsworld.ingest.live_game import game_view
    gid = game_id.removeprefix(f"{cid}-")
    try:
        out = game_view(cid, gid)
    except Exception as exc:
        raise HTTPException(502, f"ESPN game feed unavailable: {exc}")
    history = []
    try:
        engine = getattr(_svc().trackers.get(cid), "ctx", None)
        if engine is not None:
            for f in engine.engine.store.list_forecasts(f"{cid}-{gid}"):
                history.append({"at": f.as_of.isoformat() if hasattr(f.as_of, "isoformat") else str(f.as_of), "p_home": round(float(f.probabilities.get("home", 0.5)), 4)})
    except Exception:
        pass
    out["win_probability"] = history[-400:]
    out["event_id"] = f"{cid}-{gid}"
    return _clean(out)


@router.get("/f1/live")
def f1_live(session_key: str = "latest", at: str | None = None, seconds: int = 24):
    from sportsworld.config import get_settings
    from sportsworld.ingest.live_game import f1_view
    try:
        return f1_view(session_key, at, max(4, min(seconds, 60)), token=get_settings().openf1_token)
    except Exception as exc:
        raise HTTPException(502, f"OpenF1 unavailable: {exc}")


# ---------------------------------------------------------------- SportsWorld Radio (ElevenLabs)

_voice = None


def _get_voice():
    global _voice
    if _voice is None:
        from sportsworld.config import get_settings
        from sportsworld.voice import ElevenLabsVoice
        _voice = ElevenLabsVoice(get_settings(), _repo() / "data" / "voice_cache")
    return _voice


def _names(cid: str) -> dict[str, str]:
    run = _svc().state(cid).run or {}
    return {t["team_id"]: t["name"] for t in run.get("teams") or []}


@router.get("/voice/briefing")
def voice_briefing(league: str, team: str | None = None, speak: bool = True):
    """Spoken briefing written from the engine's numbers by a fixed template; ElevenLabs only voices it."""
    from fastapi.responses import JSONResponse
    from sportsworld.live.briefing import league_briefing, team_briefing
    _league(league)
    svc = _svc()
    st = svc.state(league)
    if team:
        page = team_page(league, team)
        row = next((r for r in standings(league)["rows"] if r["team_id"] == team), None)
        text = team_briefing(league, page, row, _names(league))
    else:
        board = _with_live(league, sorted(st.board.values(), key=lambda r: r["start_time"]))
        text = league_briefing(league, st.run or {}, board, list(st.feed), _names(league))
    out: dict[str, Any] = {"text": text, "source": "template over live engine numbers", "voice": None, "audio": None}
    if speak:
        v = _get_voice()
        if not v.enabled:
            out["error"] = "ElevenLabs is not configured"
        else:
            import hashlib
            try:
                audio = v.synthesize(text)
                key = hashlib.sha1(f"{v.voice_id}|{text}".encode()).hexdigest()
                out.update({"voice": v.voice_id, "audio": f"/voice/audio/{key}.mp3", "bytes": len(audio)})
            except Exception as exc:
                out["error"] = f"ElevenLabs: {exc}"
    return JSONResponse(out)


@router.get("/voice/audio/{key}.mp3")
def voice_audio(key: str):
    from fastapi.responses import FileResponse
    if not key.isalnum() or len(key) != 40:
        raise HTTPException(404, "unknown clip")
    p = _repo() / "data" / "voice_cache" / f"{key}.mp3"
    if not p.exists():
        raise HTTPException(404, "unknown clip")
    return FileResponse(p, media_type="audio/mpeg")


@router.get("/voice/update/{league}/{index}")
def voice_update(league: str, index: int):
    """Voice one world update from the feed (by its position), for the live 'radio' mode."""
    from fastapi.responses import JSONResponse
    from sportsworld.live.briefing import update_line
    _league(league)
    feed = list(_svc().state(league).feed)
    if not (0 <= index < len(feed)):
        raise HTTPException(404, "no such update")
    text = update_line(feed[index])
    v = _get_voice()
    out: dict[str, Any] = {"text": text, "audio": None}
    if v.enabled:
        import hashlib
        try:
            v.synthesize(text)
            out["audio"] = f"/voice/audio/{hashlib.sha1(f'{v.voice_id}|{text}'.encode()).hexdigest()}.mp3"
        except Exception as exc:
            out["error"] = str(exc)
    return JSONResponse(out)


# ---------------------------------------------------------------- history (Neon)

@router.get("/history/team/{cid}/{team_id}")
def team_history(cid: str, team_id: str):
    """What SportsWorld believed about this team at every archived season run (Neon Postgres)."""
    _league(cid)
    if _archive is None or not _archive.ready:
        raise HTTPException(503, "history archive not configured")
    return {"league": cid, "team_id": team_id, "source": "Neon Postgres season_run archive", "points": _archive.team_history(cid, team_id)}


@router.get("/history/game/{event_id}")
def game_history(event_id: str):
    if _archive is None or not _archive.ready:
        raise HTTPException(503, "history archive not configured")
    return {"event_id": event_id, "points": _archive.game_history(event_id)}
