"""Competition-season API (spec v3.0 §21.1, Appendix E)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
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
    if index < 0:
        index = len(feed) + index
    if not (0 <= index < len(feed)):
        raise HTTPException(404, "no such update")
    run = _svc().state(league).run or {}
    abbr = {t.get("abbreviation"): t["name"] for t in run.get("teams") or [] if t.get("abbreviation")}
    text = update_line(feed[index], abbr)
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


@router.get("/voice/game/{league}/{event_id}")
def voice_game(league: str, event_id: str):
    """Voice the current state of one live game (score + SportsWorld win probability), text built server-side."""
    from fastapi.responses import JSONResponse
    from sportsworld.live.briefing import live_game_line
    _league(league)
    st = _svc().state(league)
    row = st.board.get(event_id)
    if row is None:
        raise HTTPException(404, "game not on the board")
    row = _with_live(league, [row])[0]
    text = live_game_line(row, _names(league))
    out: dict[str, Any] = {"text": text, "audio": None}
    v = _get_voice()
    if v.enabled:
        import hashlib
        try:
            v.synthesize(text)
            out["audio"] = f"/voice/audio/{hashlib.sha1(f'{v.voice_id}|{text}'.encode()).hexdigest()}.mp3"
        except Exception as exc:
            out["error"] = str(exc)
    return JSONResponse(out)


@router.get("/voice/intro/{league}")
def voice_intro(league: str):
    from fastapi.responses import JSONResponse
    _league(league)
    text = f"SportsWorld Radio is on for {LEAGUES[league].display_name}. You will hear every final and every big swing in a live game as it happens."
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


@router.get("/voice/commentary/{league}/{event_id}")
def voice_commentary(league: str, event_id: str, after: str | None = None):
    """Live play-by-play call for one game: new plays since `after`, with SportsWorld's win probability, voiced."""
    from fastapi.responses import JSONResponse
    from sportsworld.ingest.live_game import play_stream
    from sportsworld.live.commentary import commentary
    spec = _league(league)
    gid = event_id.removeprefix(f"{league}-")
    try:
        stream = play_stream(league, gid)
    except Exception as exc:
        raise HTTPException(502, f"ESPN play-by-play unavailable: {exc}")
    row = _svc().state(league).board.get(f"{league}-{gid}")
    live_score = None
    if row is not None:
        row = _with_live(league, [row])[0]
        if row.get("state") == "in" and row.get("home_score") is not None:
            live_score = (int(row.get("away_score") or 0), int(row.get("home_score") or 0))
    out = commentary(f"{league}-{gid}", spec.sport.value, stream, row.get("p_home") if row else None, after, live_score=live_score)
    text = " ".join(x["text"] for x in out["lines"])
    out["audio"] = None
    if text:
        v = _get_voice()
        if v.enabled:
            import hashlib
            try:
                v.synthesize(text)
                out["audio"] = f"/voice/audio/{hashlib.sha1(f'{v.voice_id}|{text}'.encode()).hexdigest()}.mp3"
            except Exception as exc:
                out["error"] = str(exc)
    return JSONResponse(out)


# ---------------------------------------------------------------- Ask SportsWorld (same analyst as the Fetch.ai agent)

class AgentAskIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


_analyst_engine = None


@router.post("/agent/ask")
def agent_ask(body: AgentAskIn):
    """The SportsWorld Analyst (also on Agentverse / ASI:One): routes a question to actions on this engine."""
    global _analyst_engine
    from sportsworld.agent.analyst import Engine, answer
    if _analyst_engine is None:
        _analyst_engine = Engine()
    structured = answer(body.text, _analyst_engine)
    import hashlib
    aid = hashlib.sha1(f"{body.text}|{structured}".encode()).hexdigest()[:16]
    _answers[aid] = (body.text, structured)
    while len(_answers) > 500:
        _answers.pop(next(iter(_answers)))
    return {"answer": structured, "answer_id": aid, "agent": "sportsworld-analyst"}


_answers: dict[str, tuple[str, str]] = {}


@router.get("/agent/rephrase/{answer_id}")
def agent_rephrase(answer_id: str):
    """Conversational version of an answer the engine just produced (only by id: this is not a general LLM endpoint).
    Every number in the prose is checked against the engine's answer; on any mismatch prose is null."""
    item = _answers.get(answer_id)
    if item is None:
        raise HTTPException(404, "unknown answer")
    from sportsworld.agent.converse import rewrite
    prose = rewrite(*item)
    return {"prose": prose, "checked": prose is not None,
            "note": "Written by self-hosted Llama 3.3 from the engine's answer; every number verified." if prose else None}


@router.get("/research/scorecard/{cid}")
def research_scorecard(cid: str, date: str | None = None):
    """How today's (or `date`'s, US Eastern) pregame forecasts did vs results, next to ESPN and the market."""
    _league(cid)
    from zoneinfo import ZoneInfo
    from sportsworld.live.scorecard import scorecard
    svc = _svc()
    if date:
        return _clean(scorecard(cid, date, svc._games(cid), svc.registry, _repo()))
    # today, or the most recent day with finished games (mornings, off days)
    today = datetime.now(ZoneInfo("America/New_York")).date()
    for back in range(0, 8):
        day = (today - timedelta(days=back)).isoformat()
        out = scorecard(cid, day, svc._games(cid), svc.registry, _repo())
        if out["games"]:
            return _clean({**out, "is_today": back == 0})
    return _clean({**out, "is_today": True})


@router.get("/games/{cid}/{game_id}/boxscore")
def game_boxscore(cid: str, game_id: str):
    _league(cid)
    from sportsworld.ingest.live_game import box_score
    try:
        return box_score(cid, game_id.removeprefix(f"{cid}-"), _svc().data_root)
    except Exception as exc:
        raise HTTPException(502, f"ESPN box score unavailable: {exc}")


@router.get("/entities/team/{cid}/{team_id}/player-stats")
def team_player_stats(cid: str, team_id: str):
    """Season player stats for one team, summed from the box score of every completed game this season."""
    spec = _league(cid)
    from sportsworld.ingest.espn import season_start_year
    from sportsworld.ingest.live_game import season_stats
    svc = _svc()
    games = [g for g in svc._games(cid) if g.completed and team_id in (g.home.team_id, g.away.team_id) and g.season_type in (2, 3)]
    if not games:
        return {"league": cid, "team_id": team_id, "games": 0, "categories": []}
    season = max(season_start_year(spec, g.start_time) for g in games)
    ids = [g.game_id for g in sorted(games, key=lambda g: g.start_time) if season_start_year(spec, g.start_time) == season]
    return season_stats(cid, team_id, ids, svc.data_root)


MILESTONE_NAME = {"playoffs": "playoff", "tournament": "NCAA tournament", "qualify": "playoff", "make_playoffs": "playoff"}


def _stakes(cid: str, row: dict, teams: dict[str, dict]) -> dict:
    """Why one game matters: win probability, both teams' playoff swing, who else it moves, and a viewing call."""
    p = row.get("live_p_home") if row.get("state") == "in" and row.get("live_p_home") is not None else row.get("p_home")
    p = 0.5 if p is None else float(p)
    lh, la = float(row.get("leverage_home") or 0), float(row.get("leverage_away") or 0)
    ms = row.get("leverage_milestone") or "playoffs"
    mname = MILESTONE_NAME.get(ms, ms.replace("_", " "))
    poss = lambda n: n + ("'" if n.endswith("s") else "'s")  # noqa: E731
    fav, dog, pf = (row["home"], row["away"], p) if p >= 0.5 else (row["away"], row["home"], 1 - p)
    swing = max(abs(lh), abs(la))
    who = row["home"] if abs(lh) >= abs(la) else row["away"]
    if row.get("state") == "post":
        action, tone = "Final. The result is already folded into every season forecast.", "final"
    elif row.get("state") == "in" and pf >= 0.97:
        action, tone = f"Effectively decided: {fav} at {pf * 100:.0f}%. The {mname} swing of {swing * 100:.0f} pts is already priced into every forecast.", "low"
    elif row.get("state") == "in" and 0.25 <= p <= 0.75 and swing >= 0.03:
        action, tone = f"Tune in now: still in doubt, with up to {swing * 100:.0f} pts of {mname} odds riding on it.", "must"
    elif swing >= 0.10 and pf < 0.7:
        action, tone = f"Must-watch: a real contest that moves {poss(who)} {mname} odds by {swing * 100:.0f} pts.", "must"
    elif swing >= 0.10:
        action, tone = f"Watch for the upset: {fav} should win ({pf * 100:.0f}%), but a {dog} win would swing {poss(who)} {mname} odds by {swing * 100:.0f} pts. Check in if it is close late.", "upset"
    elif swing >= 0.03:
        action, tone = f"Worth a look: it moves {poss(who)} {mname} odds by {swing * 100:.0f} pts.", "look"
    elif pf < 0.6:
        action, tone = "Good game, low stakes: evenly matched, but little changes for the season either way.", "low"
    else:
        action, tone = "Skip it for the season picture: little is at stake either way.", "skip"
    # each side's odds if it wins / loses: now = p*W + (1-p)*L and W - L = swing
    def split(now, swing, pw):
        if now is None:
            return None, None
        w, l = now + (1 - pw) * swing, now - pw * swing
        return round(min(1, max(0, w)), 4), round(min(1, max(0, l)), 4)
    th, ta = teams.get(row["home_id"], {}), teams.get(row["away_id"], {})
    hw, hl = split(th.get(ms), lh, p)
    aw, al = split(ta.get(ms), la, 1 - p)
    ripple = []
    for r in row.get("ripple") or []:
        t = teams.get(r["team_id"], {})
        d = float(r["delta_if_home_wins"])
        rooted = row["home"] if d > 0 else row["away"]
        hurt = row["away"] if d > 0 else row["home"]
        hurt_t = th if hurt == row["home"] else ta
        now_t = t.get(ms)
        if t.get("conference") and t.get("conference") == hurt_t.get("conference"):
            why = f"{t['conference'].replace(' Conference', '')} rival"
        elif now_t is not None and 0.05 <= now_t <= 0.95:
            why = f"on the {mname} bubble"
        else:
            why = f"in the {mname} race"
        ripple.append({"team_id": r["team_id"], "name": t.get("name", r["team_id"]), "now": now_t,
                       "if_home_wins": d, "roots_for": rooted, "why": why})
    # one plain-English reason, built only from the numbers above
    side = ("home", row["home"], hw, hl) if abs(lh) >= abs(la) else ("away", row["away"], aw, al)
    _, team_name, w_, l_ = side
    pct_ = lambda x: f"{x * 100:.0f}%" if x is not None else "-"  # noqa: E731
    if row.get("state") == "post":
        reason = "This game is final; its result is already part of every forecast."
    elif swing < 0.03 or w_ is None:
        reason = f"Little rides on this one for the {mname} race: neither team's odds move by more than {max(swing * 100, 1):.0f} pts either way."
    else:
        reason = f"{poss(team_name)} {mname} hopes ride on this one: {pct_(w_)} with a win, {pct_(l_)} with a loss."
        if ripple:
            r0 = ripple[0]
            reason += f" {r0['name']} ({r0['why']}) should be rooting for {r0['roots_for']}."
    return {"event_id": row["event_id"], "state": row.get("state"), "home": row["home"], "away": row["away"],
            "home_id": row["home_id"], "away_id": row["away_id"], "p_home": round(p, 4), "favourite": fav, "p_favourite": round(pf, 4),
            "milestone": ms, "milestone_name": mname,
            "home_now": teams.get(row["home_id"], {}).get(ms), "away_now": teams.get(row["away_id"], {}).get(ms),
            "swing_home": round(lh, 4), "swing_away": round(la, 4), "affected": ripple, "action": action, "tone": tone,
            "home_if_win": hw, "home_if_lose": hl, "away_if_win": aw, "away_if_lose": al, "reason": reason,
            "as_of": row.get("as_of"), "global_state_version": row.get("global_state_version")}


@router.get("/games/{cid}/{event_id}/stakes")
def game_stakes(cid: str, event_id: str):
    _league(cid)
    st = _svc().state(cid)
    eid = event_id if event_id.startswith(f"{cid}-") else f"{cid}-{event_id}"
    row = st.board.get(eid) or next((r for r in st.board.values() if r["event_id"] in (eid, event_id)), None)
    if row is None or st.fast_run is None:
        raise HTTPException(404, "game not on the season board (finished earlier, or no season run yet)")
    row = _with_live(cid, [row])[0]
    return _clean(_stakes(cid, row, {t["team_id"]: t for t in st.fast_run["teams"]}))


@router.get("/competitions/{cid}/game-of-the-day")
def game_of_the_day(cid: str):
    """The upcoming or live game with the most season at stake, weighted toward games still in doubt."""
    _league(cid)
    st = _svc().state(cid)
    if st.fast_run is None:
        raise HTTPException(404, "no season run yet")
    rows = [r for r in _with_live(cid, list(st.board.values())) if r.get("state") in ("pre", "in")]
    soon = [r for r in rows if r.get("state") == "in" or r["start_time"] <= (datetime.now(timezone.utc) + timedelta(days=8)).isoformat()] or rows
    def score(r):
        p = r.get("live_p_home") if r.get("state") == "in" and r.get("live_p_home") is not None else (r.get("p_home") or 0.5)
        return max(abs(r.get("leverage_home") or 0), abs(r.get("leverage_away") or 0)) * 4 * p * (1 - p)
    if not soon:
        raise HTTPException(404, "no upcoming games")
    best = max(soon, key=score)
    return _clean(_stakes(cid, best, {t["team_id"]: t for t in st.fast_run["teams"]}))


_REWIND: dict | None = None


@router.get("/research/rewind")
def research_rewind():
    """What the model gave each eventual champion at each checkpoint, frozen at that date (point-in-time replays)."""
    global _REWIND
    if _REWIND is not None:
        return _REWIND
    from sportsworld.ingest.espn import drop_exhibitions, read_archive, season_start_year
    root = _repo() / "data" / "fixtures" / "backtests"
    out = []
    for lg in ("nfl", "college-football", "nba", "nhl"):
        p = root / f"season_{lg}_ext.json"
        if not p.exists():
            continue
        rows = [r for r in json.loads(p.read_text())["rows"] if r["mode"] == "dynamic"]
        spec = LEAGUES[lg]
        games = [g for g in drop_exhibitions(read_archive(_repo() / "data" / "real", lg)) if g.completed and g.season_type == 3]
        champ: dict[int, str] = {}
        for g in sorted(games, key=lambda g: g.start_time):  # the last postseason game of a season is its final
            champ[season_start_year(spec, g.start_time)] = g.home.name if g.home.score > g.away.score else g.away.name
        for season in sorted({r["season"] for r in rows}):
            cps = sorted((r for r in rows if r["season"] == season), key=lambda r: r["checkpoint"])
            if not champ.get(season) or any(r.get("champion_prob") is None for r in cps):
                continue  # disrupted calendars (2019-20 / 2020-21 bubble seasons) have no valid replay
            out.append({"league": lg, "league_name": spec.display_name, "season": season, "champion": champ.get(season),
                        "teams": cps[0]["teams"], "uniform": round(1 / cps[0]["teams"], 4),
                        "checkpoints": [{"checkpoint": r["checkpoint"], "as_of": r["as_of"], "champion_prob": r.get("champion_prob")} for r in cps]})
    _REWIND = _clean({"rows": out, "method": ("Each checkpoint is a full rebuild of the competition as it stood on that date: only results known "
                                              "by then, rating hyper-parameters fit on earlier seasons only, the schedule as published. Results "
                                              "enter the ratings only once they are final (backend/tests/test_real_ingest.py checks a game cannot "
                                              "see a result that finishes after it starts).")})
    return _REWIND


@router.get("/entities/team/{cid}/{team_id}/regulars")
def team_regulars(cid: str, team_id: str):
    """This team's regulars and each one's learned absence effect (for the Lab's player menu)."""
    _league(cid)
    p = _repo() / "models" / "artifacts" / "player_impact" / f"{cid}.json"
    if not p.exists():
        return {"league": cid, "team_id": team_id, "players": []}
    art = json.loads(p.read_text())
    by_pos = art.get("by_position", {})
    label = {"QB": "starting QB", "G": "starting goalie", "KEY": "top-minutes player", "RB1": "lead running back", "WR1": "top receiver", "DEF1": "top tackler"}
    out, seen = [], set()
    for pos, players in (art.get("current_key_players") or {}).get(team_id, {}).items():
        est = by_pos.get(pos) or {}
        if pos in ("RB1", "WR1", "DEF1") and art.get("share_effects"):
            continue  # football skill players are valued by their share below
        for pl in players:
            if est.get("points") is None or pl["name"] in seen:
                continue
            seen.add(pl["name"])
            out.append({"name": pl["name"], "role": pos, "label": label.get(pos, pos), "share": None,
                        "points": round(est["points"], 3), "se": round(est.get("se", 0), 3), "significant": bool(est.get("significant", True))})
    se_ = art.get("share_effects") or {}
    words = {"RUSH": "carries", "REC": "catches", "DEF": "tackles"}
    best: dict[str, dict] = {}
    for role, players in (se_.get("current_shares") or {}).get(team_id, {}).items():
        est = (se_.get("by_role") or {}).get(role) or {}
        for pl in players:
            if pl["name"] in seen:
                continue
            row = {"name": pl["name"], "role": role, "label": f"{pl['share'] * 100:.0f}% of team {words.get(role, role)}", "share": pl["share"],
                   "points": round(est.get("points_per_full_share", 0) * pl["share"], 3), "se": round(est.get("se", 0) * pl["share"], 3),
                   "significant": bool(est.get("significant"))}
            if pl["name"] not in best or abs(row["points"]) > abs(best[pl["name"]]["points"]):
                best[pl["name"]] = row
    out += sorted(best.values(), key=lambda r: r["points"])
    return {"league": cid, "team_id": team_id, "players": out,
            "note": "Offensive linemen record no box-score stats, so their absences cannot be measured; use a strength override."}
