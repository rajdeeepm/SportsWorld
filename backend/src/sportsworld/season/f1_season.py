"""F1 driver + constructor championship Monte Carlo (spec v3.0 §7.5, §16.4).

Per draw:  driver_i ~ N(mu_d, var_d),  car_c ~ N(mu_c, var_c)   (teammates share the car draw)
Per remaining race (and sprint): performance_i = driver_i + car_c(i) + N(0, obs_sd^2); DNF_i ~ Bernoulli(1 - reliability_c)
Classified order = descending performance among finishers (Thurstone model, matching the
rating book's observation model); points by the season's scoring rules; latent states drift by q per race.
Standings tie-break: points, then wins, then random (APPROX of count-back).
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from sportsworld.ingest.f1 import JOLPICA, F1Params, F1RatingBook, read_f1_archive

RULES_VERSION = "f1_rules_2026_v1"
SIMULATOR_VERSION = "f1_season_sim_v1"
RACE_POINTS = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]
SPRINT_POINTS = [8, 7, 6, 5, 4, 3, 2, 1]


async def fetch_f1_season_state(season: int, root: Path) -> dict:
    """Calendar (with sprint flags) + official driver/constructor standings + sprint results; cached."""
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "SportsWorld/1.3"}) as c:
        async def get(path):
            r = await c.get(f"{JOLPICA}/{path}")
            r.raise_for_status()
            return r.json()["MRData"]
        cal = (await get(f"{season}.json?limit=100"))["RaceTable"]["Races"]
        last = (await get(f"{season}/last/results.json?limit=100"))["RaceTable"]["Races"]
        ds = (await get(f"{season}/driverStandings.json?limit=100"))["StandingsTable"]["StandingsLists"]
        cs = (await get(f"{season}/constructorStandings.json?limit=100"))["StandingsTable"]["StandingsLists"]
    state = {
        "season": season, "fetched_at": datetime.now(timezone.utc).isoformat(),
        "calendar": [{"round": int(r["round"]), "name": r["raceName"], "circuit": r["Circuit"]["circuitName"],
                      "start": f"{r['date']}T{r.get('time', '12:00:00Z')}", "sprint": "Sprint" in r} for r in cal],
        "standings_round": int(ds[0]["round"]) if ds else 0,
        "drivers": [{"driver_id": x["Driver"]["driverId"], "code": x["Driver"].get("code"), "name": f"{x['Driver']['givenName']} {x['Driver']['familyName']}",
                     "constructor_id": x["Constructors"][-1]["constructorId"] if x.get("Constructors") else None,
                     "points": float(x["points"]), "wins": int(x["wins"]), "position": int(x.get("position") or 99)} for x in (ds[0]["DriverStandings"] if ds else [])],
        "constructors": [{"constructor_id": x["Constructor"]["constructorId"], "name": x["Constructor"]["name"], "points": float(x["points"]),
                          "wins": int(x["wins"]), "position": int(x.get("position") or 99)} for x in (cs[0]["ConstructorStandings"] if cs else [])],
    }
    # Current entry list (two cars per constructor): drivers who started the latest round.
    state["entries"] = [{"driver_id": r["Driver"]["driverId"], "constructor_id": r["Constructor"]["constructorId"]} for r in (last[0]["Results"] if last else [])]
    state["entries_round"] = int(last[0]["round"]) if last else None
    p = root / "f1" / "season" / f"{season}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=1))
    return state


def load_f1_season_state(season: int, root: Path) -> dict | None:
    p = root / "f1" / "season" / f"{season}.json"
    return json.loads(p.read_text()) if p.exists() else None


def _repo() -> Path:
    return Path(__file__).resolve().parents[4]


def build_f1_book(root: Path, as_of: datetime) -> F1RatingBook:
    meta = _repo() / "models" / "artifacts" / "ratings" / "f1.json"
    params = F1Params(**json.loads(meta.read_text())["params"]) if meta.exists() else F1Params()
    book = F1RatingBook(params)
    for race in read_f1_archive(root):
        if race.completed and race.start_time < as_of:
            book.apply_race(race)
    return book


def run_f1_season(state: dict, book: F1RatingBook, *, draws: int = 10_000, seed: int = 7, mode: str = "dynamic",
                  rating_shifts: dict[str, float] | None = None, from_round: int | None = None, label: str | None = None) -> dict[str, Any]:
    """rating_shifts: constructor_id or driver_id -> delta (finishing-score units) from `from_round` on."""
    t0 = time.perf_counter()
    rng = np.random.default_rng(seed)
    p = book.p
    entries = {e["driver_id"]: e["constructor_id"] for e in state.get("entries", [])}
    drivers = [dict(d) for d in state["drivers"]]
    for d in drivers:  # a driver racing for a new team scores for that team from now on
        if d["driver_id"] in entries:
            d["constructor_id"] = entries[d["driver_id"]]
    n = len(drivers)
    entered = np.asarray([(not entries) or d["driver_id"] in entries for d in drivers])
    cons = sorted({d["constructor_id"] for d in drivers})
    ci = np.asarray([cons.index(d["constructor_id"]) for d in drivers])
    d_mu = np.zeros(n); d_var = np.zeros(n)
    for i, d in enumerate(drivers):
        lat = book.drivers.get(d["driver_id"])
        d_mu[i], d_var[i] = (lat.mean, lat.var) if lat else (-0.2, p.init_var_driver)
    c_mu = np.zeros(len(cons)); c_var = np.zeros(len(cons)); rel = np.zeros(len(cons))
    for j, c in enumerate(cons):
        lat = book.cars.get(c)
        c_mu[j], c_var[j] = (lat.mean, lat.var) if lat else (-0.2, p.init_var_car)
        rel[j] = max(0.5, min(0.995, lat.finishes / lat.starts)) if lat else 0.85
    if mode == "dynamic":
        drv = d_mu[None, :] + np.sqrt(d_var)[None, :] * rng.standard_normal((draws, n))
        car = c_mu[None, :] + np.sqrt(c_var)[None, :] * rng.standard_normal((draws, len(cons)))
    else:
        drv = np.repeat(d_mu[None, :], draws, 0)
        car = np.repeat(c_mu[None, :], draws, 0)
    shift_d = np.zeros(n)
    for key, delta in (rating_shifts or {}).items():
        shift_d += np.where(ci == (cons.index(key) if key in cons else -1), delta, 0.0)
        shift_d += np.asarray([delta if d["driver_id"] == key else 0.0 for d in drivers])
    remaining = [r for r in state["calendar"] if r["round"] > state["standings_round"]]
    pts = np.repeat(np.asarray([d["points"] for d in drivers])[None, :], draws, 0)
    wins = np.repeat(np.asarray([d["wins"] for d in drivers], float)[None, :], draws, 0)
    race_win_counts = np.zeros((len(remaining), n))
    podiums = np.zeros((draws, n))
    rows = np.arange(draws)[:, None]

    pos_counts = np.zeros((draws, n, 10))  # FIA count-back: number of 1st, 2nd, ... 10th places
    pos_counts[:, :, 0] = np.asarray([d["wins"] for d in drivers], float)[None, :]

    def session(points_table, extra_shift):
        perf = drv + car[:, ci] + extra_shift[None, :] + p.obs_sd * rng.standard_normal((draws, n))
        dnf = rng.random((draws, n)) > rel[ci][None, :]
        perf = np.where(dnf | ~entered[None, :], -np.inf, perf)  # non-entrants never score
        order = np.argsort(-perf, axis=1)
        gained = np.zeros((draws, n))
        for k, val in enumerate(points_table[:n]):
            finisher = np.isfinite(perf[rows[:, 0], order[:, k]])
            gained[rows[:, 0], order[:, k]] += val * finisher
        return order, gained, dnf

    for idx, race in enumerate(remaining):
        if mode == "dynamic" and idx > 0:
            drv = drv + math.sqrt(p.q_driver) * rng.standard_normal(drv.shape)
            car = car + math.sqrt(p.q_car) * rng.standard_normal(car.shape)
        extra = shift_d if (from_round is None or race["round"] >= from_round) else np.zeros(n)
        if race["sprint"]:
            _, g, _ = session(SPRINT_POINTS, extra)
            pts += g
        order, g, _ = session(RACE_POINTS, extra)
        pts += g
        for k in range(min(10, n)):
            pos_counts[np.arange(draws), order[:, k], k] += 1
        winner = order[:, 0]
        wins[np.arange(draws), winner] += 1
        race_win_counts[idx] = np.bincount(winner, minlength=n) / draws
        for k in range(3):
            podiums[np.arange(draws), order[:, k]] += 1
    countback = sum(pos_counts[:, :, k] * (30.0 ** -(k + 1)) for k in range(10))
    dkey = pts + 1e-2 * countback + 1e-12 * rng.random(pts.shape)
    drank = np.argsort(np.argsort(-dkey, axis=1), axis=1) + 1
    cpts = np.zeros((draws, len(cons)))
    for j in range(len(cons)):
        cpts[:, j] = pts[:, ci == j].sum(axis=1)
    base_c = {c["constructor_id"]: c["points"] for c in state["constructors"]}
    base_from_drivers = {cons[j]: sum(d["points"] for d, k in zip(drivers, ci) if k == j) for j in range(len(cons))}
    for j, c in enumerate(cons):  # driver swaps mid-season: constructor table is authoritative for banked points
        cpts[:, j] += base_c.get(c, 0.0) - base_from_drivers[c]
    ccount = np.zeros((draws, len(cons)))
    for j in range(len(cons)):
        ccount[:, j] = countback[:, ci == j].sum(axis=1)
    ckey = cpts + 1e-2 * ccount + 1e-12 * rng.random(cpts.shape)
    crank = np.argsort(np.argsort(-ckey, axis=1), axis=1) + 1
    se = lambda q: round(math.sqrt(max(q * (1 - q), 0) / draws), 4)  # noqa: E731
    driver_rows = []
    for i, d in enumerate(drivers):
        title = float((drank[:, i] == 1).mean())
        driver_rows.append({
            **{k: d[k] for k in ("driver_id", "code", "name", "constructor_id")}, "points_now": d["points"], "wins_now": d["wins"],
            "rating": round(float(d_mu[i] + c_mu[ci[i]]), 3), "rating_sd": round(float(math.sqrt(d_var[i] + c_var[ci[i]])), 3),
            "reliability": round(float(rel[ci[i]]), 3), "expected_points": round(float(pts[:, i].mean()), 1),
            "points_p05": float(np.quantile(pts[:, i], .05)), "points_p95": float(np.quantile(pts[:, i], .95)),
            "expected_wins": round(float(wins[:, i].mean()), 2), "expected_podiums_remaining": round(float(podiums[:, i].mean()), 2),
            "title": round(title, 4), "title_se": se(title),
            "rank_dist": [round(float((drank[:, i] == k).mean()), 4) for k in range(1, min(n, 10) + 1)],
        })
    driver_rows.sort(key=lambda r: (r["title"], r["expected_points"]), reverse=True)
    names = {c["constructor_id"]: c["name"] for c in state["constructors"]}
    cons_rows = []
    for j, c in enumerate(cons):
        title = float((crank[:, j] == 1).mean())
        cons_rows.append({"constructor_id": c, "name": names.get(c, c), "points_now": base_c.get(c, 0.0), "car_rating": round(float(c_mu[j]), 3),
                          "reliability": round(float(rel[j]), 3), "expected_points": round(float(cpts[:, j].mean()), 1),
                          "points_p05": float(np.quantile(cpts[:, j], .05)), "points_p95": float(np.quantile(cpts[:, j], .95)),
                          "title": round(title, 4), "title_se": se(title),
                          "rank_dist": [round(float((crank[:, j] == k).mean()), 4) for k in range(1, len(cons) + 1)]})
    cons_rows.sort(key=lambda r: (r["title"], r["expected_points"]), reverse=True)
    races = [{"round": r["round"], "name": r["name"], "sprint": r["sprint"], "start": r["start"],
              "win_probabilities": {drivers[i]["code"]: round(float(race_win_counts[k, i]), 4) for i in np.argsort(-race_win_counts[k])[:8]}}
             for k, r in enumerate(remaining)]
    return {
        "league": "f1", "season": state["season"], "standings_round": state["standings_round"], "mode": mode, "draws": draws, "seed": seed,
        "rules_version": RULES_VERSION, "simulator_version": SIMULATOR_VERSION, "rating_params": p.to_dict(), "scenario": label,
        "drivers": driver_rows, "constructors": cons_rows, "remaining_races": races,
        "entry_list": {"round": state.get("entries_round"), "drivers": int(entered.sum()), "note": "non-entered drivers keep banked points but do not start future races"},
        "diagnostics": {"runtime_s": round(time.perf_counter() - t0, 3), "remaining_races": len(remaining), "remaining_sprints": sum(r["sprint"] for r in remaining),
                        "driver_champions_per_draw": int((drank == 1).sum(axis=1).max()), "constructor_champions_per_draw": int((crank == 1).sum(axis=1).max())},
    }
