"""SeasonService: all-event forecast scheduler + invalidation + season recompute (spec v3.0 §15).

Per league it keeps
  * board: a calibrated forecast for EVERY remaining scheduled game of the season (not just
    games someone opened), each stamped with global_state_version / model version / as_of;
  * season run: the latest DYNAMIC 10k-draw season Monte Carlo (and a FAST run for comparison);
  * a world-update feed explaining which evidence changed what.

Invalidation graph (implemented edges):
  game final -> both teams' latent ratings (tracker book) -> every future game involving
  either team (board rows reforecast) -> league season run (debounced recompute) -> WebSocket.
  F1 race classified -> driver/car ratings -> remaining races + championship run.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from sportsworld.ingest.espn import GameRecord, read_archive
from sportsworld.ingest.features import league_features
from sportsworld.ingest.leagues import LEAGUES
from sportsworld.ingest.ratings import RatingBook

from .engine import SeasonScenario, build_setup, run_season
from .f1_season import build_f1_book, load_f1_season_state, run_f1_season

log = logging.getLogger("sportsworld.season")


class LeagueSeasonState:
    def __init__(self, league: str):
        self.league = league
        self.global_state_version = 0
        self.dirty = True
        self.reasons: list[str] = []
        self.board: dict[str, dict] = {}
        self.run: dict | None = None
        self.fast_run: dict | None = None
        self.run_version = 0
        self.computing = False
        self.feed: deque[dict] = deque(maxlen=60)
        self.last_error: str | None = None
        self.last_live_trigger = 0.0


class SeasonService:
    def __init__(self, data_root: Path, registry, *, trackers: dict | None = None, publish: Callable[[str, str, dict], None] | None = None,
                 draws: int = 10_000, debounce_s: float = 5.0, as_of: datetime | None = None):
        self.fixed_as_of = as_of  # offline historical replay: every run is reconstructed at this instant
        self.data_root = data_root
        self.registry = registry
        self.trackers = trackers or {}
        self.publish = publish
        self.draws = draws
        self.debounce_s = debounce_s
        self.states: dict[str, LeagueSeasonState] = {}
        self._task: asyncio.Task | None = None
        self.availability = None  # ingest.availability.AvailabilityService
        self.active: set[str] | None = None  # leagues with a season simulation (set by start)

    def on_live(self, league: str) -> None:
        """Live score/clock change: re-condition the season run on in-progress games (rate-limited to 1/min)."""
        if self.active is not None and league not in self.active:
            return
        st = self.state(league)
        if time.time() - st.last_live_trigger >= 60:
            st.last_live_trigger = time.time()
            st.global_state_version += 1
            st.dirty = True

    def on_availability(self, league: str, changed: dict[str, dict]) -> None:
        """Entity-availability recompute class (spec §15.3): every future game of the team + season."""
        for tid, rec in changed.items():
            names = ", ".join(f"{a['player']} ({a['role']}) {a['status']}" for a in rec["absences"]) or "all key players available"
            self.invalidate(league, f"Availability: {names} -> {rec['delta_points']:+.1f} pts", [tid],
                            {"availability": rec})
        tr = self.trackers.get(league)
        if tr is not None and hasattr(tr, "refresh_availability"):
            tr.refresh_availability(set(changed), f"availability report ({len(changed)} teams)")

    def _availability_scenario(self, league: str, setup) -> SeasonScenario | None:
        if self.fixed_as_of is not None:
            return None  # historical replay: today's injury report is not point-in-time evidence
        book = self.availability.books.get(league) if self.availability else None
        if not book or book.is_stale():
            return None
        shifts = []
        for tid, rec in book.deltas.items():
            if not rec["delta_points"]:
                continue
            idx = setup.index().get(tid)
            if idx is None:
                continue
            nxt = next((t for h, a, t in zip(setup.r_home, setup.r_away, setup.r_start) if idx in (h, a)), None)
            anchor = datetime.fromisoformat(str(rec.get("window_anchor") or book.fetched_at.isoformat()).replace("Z", "+00:00"))
            if anchor.tzinfo is None:
                anchor = anchor.replace(tzinfo=timezone.utc)
            end = (anchor + __import__("datetime").timedelta(days=rec["window_days"])) if rec.get("window_days") else nxt
            if end is not None:
                shifts.append((tid, rec["delta_points"], None, end))
        return SeasonScenario(rating_shifts=shifts, label="live availability") if shifts else None

    # ------------------------------------------------------------------
    def state(self, league: str) -> LeagueSeasonState:
        return self.states.setdefault(league, LeagueSeasonState(league))

    def invalidate(self, league: str, reason: str, teams: list[str] | None = None, detail: dict | None = None) -> None:
        if self.active is not None and league not in self.active:
            return  # no season simulation for this competition (e.g. college hockey: incomplete conference data)
        st = self.state(league)
        st.global_state_version += 1
        st.dirty = True
        st.reasons.append(reason)
        st.feed.appendleft({"at": datetime.now(timezone.utc).isoformat(), "global_state_version": st.global_state_version,
                            "reason": reason, "teams": teams or [], **(detail or {})})
        for row in st.board.values():
            if teams is None or row["home_id"] in teams or row["away_id"] in teams:
                row["freshness"] = "stale"

    # ------------------------------------------------------------------
    def _games(self, league: str) -> list[GameRecord]:
        games = {g.game_id: g for g in read_archive(self.data_root, league)}
        tr = self.trackers.get(league)
        if tr is not None and hasattr(tr, "games"):
            for g in tr.games.values():
                games[g.game_id] = g
        return list(games.values())

    def _book(self, league: str) -> RatingBook | None:
        tr = self.trackers.get(league)
        return getattr(tr, "book", None) if tr is not None and isinstance(getattr(tr, "book", None), RatingBook) else None

    def compute(self, league: str) -> dict:
        """Synchronous recompute: board for every remaining game + DYNAMIC and FAST season runs."""
        st = self.state(league)
        if league == "f1":
            return self._compute_f1(st)
        t0 = time.perf_counter()
        start_version = st.global_state_version
        now = self.fixed_as_of or datetime.now(timezone.utc)
        setup = build_setup(league, self.data_root, now, games=self._games(league), book=None if self.fixed_as_of else self._book(league))
        book = None if self.fixed_as_of else self._book(league)
        if book is None:
            from sportsworld.ingest.ratings import RatingBook as RB, load_params
            from sportsworld.ingest.espn import drop_exhibitions
            from sportsworld.ingest.ratings import result_known_time as _rk
            book = RB(LEAGUES[league], setup.params).replay(drop_exhibitions([g for g in self._games(league) if _rk(g, LEAGUES[league].sport) <= now]), until=now)
        by_id = {g.event_id: g for g in self._games(league)}
        avail = self._availability_scenario(league, setup)
        shift_end = {tid: (d, end) for tid, d, _, end in (avail.rating_shifts if avail else [])}
        rows, feats = [], []
        for eid in setup.r_event_ids:
            g = by_id[eid]
            state = book.pregame_state(g)
            for side in ("home", "away"):
                sh = shift_end.get(getattr(g, side).team_id)
                if sh and g.start_time <= sh[1]:
                    state[f"{side}_rating"] = float(state[f"{side}_rating"]) + sh[0]
            feats.append(league_features({**state, "home_score": 0, "away_score": 0, "seconds_remaining": LEAGUES[league].regulation_seconds}))
            rows.append(g)
        preds = self.registry.predict_league_features(league, feats) if feats else []
        engine = None if self.fixed_as_of else getattr(self.trackers.get(league), "ctx", None)
        for gi, g in enumerate(rows):
            if g.state == "in" and engine is not None:
                try:
                    f = engine.engine.latest_forecast(g.event_id)
                    setup.live_probs[gi] = float(f.probabilities.get("home", 0.5))
                except Exception:
                    pass
        if preds:
            import numpy as np
            setup.board_probs = np.asarray([p[0] for p in preds])
        model = self.registry.league_card(league)
        board = {}
        for i, g in enumerate(rows):
            p, lo, hi = preds[i] if preds else (None, None, None)
            board[g.event_id] = {
                "event_id": g.event_id, "start_time": g.start_time.isoformat(), "week": g.week, "state": g.state,
                "home_id": g.home.team_id, "away_id": g.away.team_id, "home": g.home.name, "away": g.away.name,
                "home_abbr": g.home.abbreviation, "away_abbr": g.away.abbreviation, "neutral_site": g.neutral_site,
                "p_home": round(setup.live_probs[i], 4) if i in setup.live_probs else (round(p, 4) if p is not None else None),
                "p_home_pregame": round(p, 4) if p is not None else None,
                "interval_90": [round(lo, 4), round(hi, 4)] if p is not None else None,
                "model_version": model.model_version if model else None, "global_state_version": st.global_state_version,
                "as_of": now.isoformat(), "freshness": "fresh",
                "live_p_home": round(setup.live_probs[i], 4) if i in setup.live_probs else None,
            }
        dyn = run_season(setup, draws=self.draws, mode="dynamic", scenario=avail)
        fast = run_season(setup, draws=self.draws, mode="fast", scenario=avail)
        for run in (dyn, fast):
            run["scenario"] = None
            run["availability_adjustments"] = [{"team_id": t, "delta_points": d, "until": e.isoformat() if e else None} for t, d, _, e in (avail.rating_shifts if avail else [])]
        sim_g = {x["event_id"]: x for x in dyn["games"]}
        # Leverage comes from the FAST run (strengths fixed at their posterior means, games independent): there,
        # P(milestone | win) - P(milestone | loss) is the effect of the result itself. In the DYNAMIC run a win is
        # also evidence that the team's sampled strength is high, which would inflate the difference.
        lev_g = {x["event_id"]: x for x in fast["games"]}
        for eid, row in board.items():
            sg, lg_ = sim_g.get(eid, {}), lev_g.get(eid, {})
            row["p_home_season_sim"] = sg.get("p_home")
            row["leverage_home"], row["leverage_away"] = lg_.get("leverage_home"), lg_.get("leverage_away")
            row["leverage_milestone"] = lg_.get("leverage_milestone")
        # Hierarchical-consistency diagnostic (spec §17.3): board-implied vs simulated expected wins.
        exp_board: dict[str, float] = {}
        for row in board.values():
            if row["p_home"] is None:
                continue
            exp_board[row["home_id"]] = exp_board.get(row["home_id"], 0.0) + row["p_home"]
            exp_board[row["away_id"]] = exp_board.get(row["away_id"], 0.0) + 1 - row["p_home"]
        st.run_version += 1
        for run, mode in ((dyn, "dynamic"), (fast, "fast")):
            run.update({"run_id": f"{league}-{setup.season}-gs{st.global_state_version}-r{st.run_version}-{mode}",
                        "global_state_version": st.global_state_version, "event_model_version": model.model_version if model else None})
        dyn["diagnostics"]["board_vs_sim_expected_wins_mad"] = _mad(dyn, exp_board, setup)
        dyn["diagnostics"]["games_conditioned_on_live_state"] = len(setup.live_probs)
        st.board, st.run, st.fast_run = board, dyn, fast
        if st.global_state_version == start_version:  # nothing arrived while computing
            st.dirty = False
            st.reasons.clear()
        else:
            dyn["status"] = "stale"  # newer evidence arrived mid-compute; the loop recomputes
        st.last_error = None
        dyn["diagnostics"]["recompute_s"] = round(time.perf_counter() - t0, 3)
        if self.fixed_as_of:
            for run in (dyn, fast):
                run["replay_as_of"] = self.fixed_as_of.isoformat()
        return dyn

    def _compute_f1(self, st: LeagueSeasonState) -> dict:
        now = datetime.now(timezone.utc)
        state = load_f1_season_state(now.year, self.data_root)
        if state is None:
            raise RuntimeError("F1 season state not cached; run scripts/fetch_f1_season.py")
        tr = self.trackers.get("f1")
        book = tr.book if tr is not None and hasattr(tr, "book") else build_f1_book(self.data_root, now)
        dyn = run_f1_season(state, book, draws=self.draws, mode="dynamic")
        fast = run_f1_season(state, book, draws=self.draws, mode="fast")
        st.run_version += 1
        for run, mode in ((dyn, "dynamic"), (fast, "fast")):
            run.update({"run_id": f"f1-{state['season']}-gs{st.global_state_version}-r{st.run_version}-{mode}", "global_state_version": st.global_state_version})
        st.run, st.fast_run, st.dirty = dyn, fast, False
        return dyn

    async def recompute(self, league: str) -> None:
        st = self.state(league)
        if st.computing:
            return
        st.computing = True
        try:
            run = await asyncio.get_running_loop().run_in_executor(None, self.compute, league)
            await asyncio.get_running_loop().run_in_executor(None, self._save_warm, st)
            if self.publish:
                self.publish(f"season:{league}", "season.forecast.updated", {"league": league, "run_id": run.get("run_id"),
                             "global_state_version": st.global_state_version, "top": (run.get("teams") or run.get("drivers") or [])[:12]})
        except Exception as exc:  # keep serving the previous run, labelled stale
            st.last_error = f"{type(exc).__name__}: {exc}"
            log.exception("season recompute failed for %s", league)
        finally:
            st.computing = False

    async def loop(self, leagues: list[str]) -> None:
        for lg in leagues:
            self.state(lg)
        while True:
            for lg in leagues:
                st = self.state(lg)
                if st.dirty and not st.computing:
                    await self.recompute(lg)
            await asyncio.sleep(self.debounce_s)

    # warm start: the last committed run per league is kept on disk, so a restarted API serves immediately
    # (labelled stale) while the first fresh recompute runs
    def _warm_path(self, league: str) -> Path:
        return self.data_root.parent / "state" / f"{league}.json"

    def _save_warm(self, st: LeagueSeasonState) -> None:
        if self.fixed_as_of or st.run is None:
            return
        import json
        p = self._warm_path(st.league)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps({"run": st.run, "fast_run": st.fast_run, "board": st.board, "global_state_version": st.global_state_version,
                                   "saved_at": datetime.now(timezone.utc).isoformat()}, default=str))
        tmp.replace(p)

    def _load_warm(self, league: str) -> None:
        import json
        p = self._warm_path(league)
        if self.fixed_as_of or not p.exists():
            return
        try:
            d = json.loads(p.read_text())
        except Exception:
            return
        st = self.state(league)
        if st.run is None:
            st.run, st.fast_run, st.board = d.get("run"), d.get("fast_run"), d.get("board") or {}
            st.global_state_version = int(d.get("global_state_version") or 0)
            st.dirty = True  # served as stale until the first fresh recompute lands

    def start(self, leagues: list[str]) -> None:
        for lg in leagues:
            self._load_warm(lg)
        self.active = set(leagues)
        self._task = asyncio.create_task(self.loop(leagues))

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    # ------------------------------------------------------------------
    def scenario(self, league: str, scenario: SeasonScenario, *, draws: int = 10_000, seed: int = 7) -> dict:
        """Season-level counterfactual on a private branch; canonical state untouched (spec §14.3).
        Both branches start from the canonical state INCLUDING live availability; only the requested
        change differs between them (common random numbers)."""
        now = self.fixed_as_of or datetime.now(timezone.utc)
        if league == "f1":
            state = load_f1_season_state(now.year, self.data_root)
            tr = self.trackers.get("f1")
            book = tr.book if tr is not None else build_f1_book(self.data_root, now)
            shifts = {t: d for t, d, _, _ in scenario.rating_shifts}
            base = run_f1_season(state, book, draws=draws, seed=seed)
            alt = run_f1_season(state, book, draws=draws, seed=seed, rating_shifts=shifts, label=scenario.label)
            return {"base": base, "scenario": alt, "deltas": _deltas(base["drivers"], alt["drivers"], "driver_id", ["title", "expected_points"])}
        setup = build_setup(league, self.data_root, now, games=self._games(league), book=None if self.fixed_as_of else self._book(league))
        avail = self._availability_scenario(league, setup)
        base_shifts = list(avail.rating_shifts) if avail else []
        base_scen = SeasonScenario(rating_shifts=base_shifts, label="canonical (live availability)") if base_shifts else None
        alt_scen = SeasonScenario(rating_shifts=base_shifts + list(scenario.rating_shifts), forced=scenario.forced, label=scenario.label)
        base = run_season(setup, draws=draws, seed=seed, scenario=base_scen)  # common random numbers: same seed for both branches
        alt = run_season(setup, draws=draws, seed=seed, scenario=alt_scen)
        keys = [k for k in ("expected_wins", "playoffs", "tournament", "division_title", "conference_title", "conference_champion", "final_four", "champion") if k in base["teams"][0]]
        return {"base": base, "scenario": alt, "deltas": _deltas(base["teams"], alt["teams"], "team_id", keys)}


def _deltas(base: list[dict], alt: list[dict], key: str, fields: list[str]) -> list[dict]:
    a = {r[key]: r for r in alt}
    out = []
    for r in base:
        o = a.get(r[key])
        if not o:
            continue
        d = {f: round(o[f] - r[f], 4) for f in fields if isinstance(r.get(f), (int, float))}
        if any(abs(v) > 1e-9 for v in d.values()):
            out.append({key: r[key], "name": r.get("name"), **d})
    return sorted(out, key=lambda x: -max(abs(v) for k, v in x.items() if isinstance(v, float)))


def _mad(run: dict, exp_board: dict[str, float], setup) -> float | None:
    """Mean |E[wins](sim) - (played wins + sum of board probabilities)| across teams."""
    if not exp_board:
        return None
    from .engine import _played_tables
    base = _played_tables(setup)
    idx = setup.index()
    diffs = []
    for t in run["teams"]:
        i = idx[t["team_id"]]
        diffs.append(abs(t["expected_wins"] - (base["wins"][i] + exp_board.get(t["team_id"], 0.0))))
    return round(sum(diffs) / len(diffs), 3) if diffs else None
