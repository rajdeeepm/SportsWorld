"""Formula 1: every race, every driver.

Sources
-------
* Jolpica (Ergast-compatible) — calendar, qualifying and classified results back
  to 1950.  Rate limit ~4 req/s, 500 req/h, so results are paged per season.
* OpenF1 — lap-level timing for 2023+.  Historical sessions are free; live
  sessions may require an OpenF1 account token (OPENF1_TOKEN).  When live timing
  is unavailable the tracker still forecasts pre-race and settles on results.

Latent state
------------
Two-level Kalman rating per race (diagonal approximation):
    y_i = driver_i + car_c(i) + e,   e ~ N(0, obs_sd^2)
where y_i = 1 - 2 (pos_i - 1)/(n - 1) for classified finishers (+1 winner, -1 last).
Driver and car states drift between races (q) and regress between seasons (rho).
Car reliability is a decayed Beta estimate of the classified-finish rate.
"""
from __future__ import annotations

import asyncio
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

JOLPICA = "https://api.jolpi.ca/ergast/f1"
OPENF1 = "https://api.openf1.org/v1"
RACE_DURATION = timedelta(hours=1, minutes=45)
UA = {"User-Agent": "SportsWorld/1.2 (MHacks research)"}


class F1Result(BaseModel):
    driver_id: str
    code: str
    name: str
    number: str | None = None
    constructor_id: str
    constructor: str
    grid: int
    position: int | None  # None = not classified
    status: str
    laps: int = 0


class F1Race(BaseModel):
    season: int
    round: int
    race_name: str
    circuit: str
    start_time: datetime
    results: list[F1Result] = Field(default_factory=list)

    @property
    def event_id(self) -> str:
        return f"f1-{self.season}-{self.round:02d}"

    @property
    def completed(self) -> bool:
        return bool(self.results)

    def winner(self) -> F1Result | None:
        return next((r for r in self.results if r.position == 1), None)


def _start(r: dict) -> datetime:
    t = r.get("time", "12:00:00Z")
    return datetime.fromisoformat(f"{r['date']}T{t}".replace("Z", "+00:00"))


def _code(driver: dict) -> str:
    return driver.get("code") or driver.get("driverId", "UNK")[:3].upper()


def parse_result(x: dict) -> F1Result:
    d, c = x["Driver"], x["Constructor"]
    status = x.get("status", "")
    classified = x.get("positionText", "").isdigit()
    return F1Result(
        driver_id=d["driverId"], code=_code(d), name=f"{d.get('givenName', '')} {d.get('familyName', '')}".strip(),
        number=d.get("permanentNumber") or x.get("number"), constructor_id=c["constructorId"], constructor=c.get("name", c["constructorId"]),
        grid=int(x.get("grid") or 0), position=int(x["position"]) if classified else None, status=status, laps=int(x.get("laps") or 0),
    )


class JolpicaClient:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client or httpx.AsyncClient(timeout=30, headers=UA)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str) -> dict:
        delay = 2.0
        for attempt in range(5):
            r = await self._client.get(f"{JOLPICA}/{path}")
            if r.status_code == 200:
                return r.json()["MRData"]
            if r.status_code == 429 or r.status_code >= 500:
                await asyncio.sleep(delay)
                delay *= 2
                continue
            r.raise_for_status()
        raise RuntimeError(f"jolpica {path} failed after retries")

    async def schedule(self, season: int) -> list[F1Race]:
        data = await self._get(f"{season}.json?limit=100")
        return [F1Race(season=season, round=int(r["round"]), race_name=r["raceName"], circuit=r["Circuit"]["circuitName"], start_time=_start(r))
                for r in data["RaceTable"]["Races"]]

    async def season_results(self, season: int) -> list[F1Race]:
        races: dict[int, F1Race] = {}
        offset = 0
        while True:
            data = await self._get(f"{season}/results.json?limit=100&offset={offset}")
            for r in data["RaceTable"]["Races"]:
                rnd = int(r["round"])
                race = races.setdefault(rnd, F1Race(season=season, round=rnd, race_name=r["raceName"], circuit=r["Circuit"]["circuitName"], start_time=_start(r)))
                race.results.extend(parse_result(x) for x in r.get("Results", []))
            offset += 100
            if offset >= int(data["total"]):
                break
            await asyncio.sleep(0.4)
        return [races[k] for k in sorted(races)]

    async def round_results(self, season: int, rnd: int) -> list[F1Result]:
        data = await self._get(f"{season}/{rnd}/results.json?limit=100")
        races = data["RaceTable"]["Races"]
        return [parse_result(x) for x in races[0].get("Results", [])] if races else []

    async def qualifying_grid(self, season: int, rnd: int) -> dict[str, int]:
        data = await self._get(f"{season}/{rnd}/qualifying.json?limit=100")
        races = data["RaceTable"]["Races"]
        if not races:
            return {}
        return {_code(q["Driver"]): int(q["position"]) for q in races[0].get("QualifyingResults", [])}


class OpenF1Client:
    def __init__(self, token: str | None = None, client: httpx.AsyncClient | None = None, min_interval: float = 0.4):
        headers = {**UA, **({"Authorization": f"Bearer {token}"} if token else {})}
        self._client = client or httpx.AsyncClient(timeout=30, headers=headers)
        self._min_interval = min_interval
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get(self, endpoint: str, **params: Any) -> list[dict]:
        delay = 3.0
        for _ in range(6):
            async with self._lock:
                wait = self._last + self._min_interval - asyncio.get_running_loop().time()
                if wait > 0:
                    await asyncio.sleep(wait)
                self._last = asyncio.get_running_loop().time()
                r = await self._client.get(f"{OPENF1}/{endpoint}", params=params)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return []
            if r.status_code in (401, 403):
                raise PermissionError(f"OpenF1 {endpoint}: {r.status_code} (live data may need OPENF1_TOKEN)")
            await asyncio.sleep(delay)
            delay = min(30.0, delay * 2)
        raise RuntimeError(f"OpenF1 {endpoint} failed after retries")

    async def race_session(self, year: int, start: datetime) -> dict | None:
        sessions = await self.get("sessions", year=year, session_name="Race")
        best = None
        for s in sessions:
            st = datetime.fromisoformat(s["date_start"])
            if abs((st - start).total_seconds()) < 36 * 3600:
                best = s
        return best


def lap_snapshot(laps: list[dict], drivers: list[dict], upto_lap: int | None = None) -> tuple[int, dict[str, dict]]:
    """Order and gap per driver after the latest lap completed by the leader.

    Uses each driver's crossing time (start of lap L+1 or start + duration of lap L).
    Drivers who have not completed the checkpoint lap are treated as retired/lapped
    behind everyone who has, ordered by laps completed.
    """
    code_of = {int(d["driver_number"]): d.get("name_acronym") or str(d["driver_number"]) for d in drivers}
    crossing: dict[str, dict[int, datetime]] = {}
    for lap in laps:
        code = code_of.get(int(lap.get("driver_number", -1)))
        if not code or not lap.get("date_start") or not lap.get("lap_number"):
            continue
        n = int(lap["lap_number"])
        start = datetime.fromisoformat(lap["date_start"])
        crossing.setdefault(code, {})[n - 1] = start  # start of lap n = end of lap n-1
        if lap.get("lap_duration"):
            crossing[code].setdefault(n, start + timedelta(seconds=float(lap["lap_duration"])))
    if not crossing:
        return 0, {}
    lead_lap = max(max(v) for v in crossing.values() if v)
    if upto_lap is not None:
        lead_lap = min(lead_lap, upto_lap)
    rows = []
    for code, cr in crossing.items():
        done = [n for n in cr if n <= lead_lap]
        if not done:
            continue
        last = max(done)
        rows.append((-last, cr[last], code))
    rows.sort()
    leader_time = rows[0][1] if rows else None
    out = {}
    for pos, (neg_last, t, code) in enumerate(rows, start=1):
        laps_down = lead_lap + neg_last
        gap = (t - leader_time).total_seconds() if laps_down == 0 and leader_time else 90.0 * laps_down + 30.0
        out[code] = {"position": pos, "gap_to_leader": round(max(0.0, gap), 3), "laps_completed": -neg_last}
    return lead_lap, out


# ---------------------------------------------------------------------------
# Rating book
# ---------------------------------------------------------------------------
@dataclass
class F1Params:
    obs_sd: float = 0.45
    q_driver: float = 0.004
    q_car: float = 0.01
    rho_driver: float = 0.8
    rho_car: float = 0.6
    season_var_car: float = 0.08
    season_var_driver: float = 0.02
    init_var_driver: float = 0.12
    init_var_car: float = 0.15
    rel_decay: float = 0.9

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Latent:
    mean: float
    var: float
    season: int
    races: int = 0
    finishes: float = 8.0
    starts: float = 9.0
    name: str = ""
    history: list = field(default_factory=list)


class F1RatingBook:
    def __init__(self, params: F1Params | None = None):
        self.p = params or F1Params()
        self.drivers: dict[str, Latent] = {}
        self.cars: dict[str, Latent] = {}
        self.driver_car: dict[str, str] = {}
        self.codes: dict[str, str] = {}
        self.races_applied = 0
        self.loglik = 0.0
        self.applied: set[str] = set()

    def _get(self, table: dict[str, Latent], key: str, season: int, init_var: float, rho: float, season_var: float, name: str) -> Latent:
        x = table.get(key)
        if x is None:
            x = table[key] = Latent(0.0, init_var, season, name=name)
        if x.season != season:
            x.mean *= rho
            x.var = min(init_var, x.var + season_var)
            x.season = season
        return x

    def driver_view(self, driver_id: str, constructor_id: str | None) -> dict[str, float]:
        d = self.drivers.get(driver_id)
        c = self.cars.get(constructor_id or self.driver_car.get(driver_id, ""))
        dm, dv = (d.mean, d.var) if d else (-0.2, self.p.init_var_driver)
        cm, cv = (c.mean, c.var) if c else (-0.2, self.p.init_var_car)
        rel = (c.finishes / c.starts) if c else 0.85
        return {"rating_driver": dm, "rating_car": cm, "rating_sd": math.sqrt(dv + cv), "reliability": max(0.3, min(0.995, rel))}

    def apply_race(self, race: F1Race) -> None:
        if race.event_id in self.applied or not race.results:
            return
        p = self.p
        n = sum(1 for r in race.results if r.position is not None)
        for r in race.results:
            d = self._get(self.drivers, r.driver_id, race.season, p.init_var_driver, p.rho_driver, p.season_var_driver, r.name)
            c = self._get(self.cars, r.constructor_id, race.season, p.init_var_car, p.rho_car, p.season_var_car, r.constructor)
            d.var = min(p.init_var_driver, d.var + p.q_driver)
            c.var = min(p.init_var_car, c.var + p.q_car)
            self.driver_car[r.driver_id] = r.constructor_id
            self.codes[r.driver_id] = r.code
            c.starts = p.rel_decay * c.starts + 1.0
            mechanical = r.position is None and not any(k in r.status.lower() for k in ("accident", "collision", "spun", "disqualified", "withdrew"))
            c.finishes = p.rel_decay * c.finishes + (0.0 if mechanical else 1.0)
            if r.position is None or n < 2:
                continue
            y = 1.0 - 2.0 * (r.position - 1) / (n - 1)
            s = d.var + c.var + p.obs_sd ** 2
            innov = y - (d.mean + c.mean)
            self.loglik += -0.5 * (math.log(2 * math.pi * s) + innov * innov / s)
            d.mean += d.var / s * innov
            c.mean += c.var / s * innov
            d.var -= d.var * d.var / s
            c.var -= c.var * c.var / s
            d.races += 1
            c.races += 1
        self.applied.add(race.event_id)
        self.races_applied += 1

    def table(self) -> list[dict]:
        rows = []
        for did, d in self.drivers.items():
            car = self.driver_car.get(did)
            v = self.driver_view(did, car)
            rows.append({"driver_id": did, "code": self.codes.get(did), "name": d.name, "constructor_id": car,
                         "constructor": self.cars[car].name if car in self.cars else car, "season": d.season,
                         "rating": round(v["rating_driver"] + v["rating_car"], 3), "driver": round(v["rating_driver"], 3),
                         "car": round(v["rating_car"], 3), "rating_sd": round(v["rating_sd"], 3), "reliability": round(v["reliability"], 3), "races": d.races})
        return sorted(rows, key=lambda r: r["rating"], reverse=True)


def fit_f1_params(races: list[F1Race]) -> tuple[F1Params, float]:
    def score(p: F1Params) -> float:
        b = F1RatingBook(p)
        for r in races:
            b.apply_race(r)
        return b.loglik / max(1, sum(1 for r in races for x in r.results if x.position))

    p = F1Params()
    best = score(p)
    grid = {"obs_sd": [0.3, 0.35, 0.4, 0.45, 0.55], "q_driver": [0.0, 0.002, 0.005, 0.01, 0.02], "q_car": [0.0, 0.005, 0.01, 0.02, 0.05],
            "rho_driver": [0.5, 0.65, 0.8, 0.9, 1.0], "rho_car": [0.2, 0.4, 0.6, 0.8, 0.9], "season_var_car": [0.02, 0.05, 0.1, 0.2, 0.4],
            "season_var_driver": [0.0, 0.01, 0.02, 0.05, 0.1]}
    for _ in range(3):
        for k, vals in grid.items():
            for v in vals:
                t = F1Params(**{**p.to_dict(), k: v})
                sc = score(t)
                if sc > best + 1e-9:
                    best, p = sc, t
    return p, best


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------
def f1_results_path(root: Path, season: int) -> Path:
    return root / "f1" / "results" / f"{season}.jsonl"


def read_f1_archive(root: Path) -> list[F1Race]:
    races: list[F1Race] = []
    for p in sorted((root / "f1" / "results").glob("*.jsonl")):
        races.extend(F1Race.model_validate_json(x) for x in p.read_text().splitlines() if x.strip())
    return sorted(races, key=lambda r: r.start_time)


def write_f1_season(root: Path, season: int, races: list[F1Race]) -> None:
    path = f1_results_path(root, season)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(r.model_dump_json() + "\n" for r in sorted(races, key=lambda r: r.round)))


def read_f1_laps(root: Path) -> dict[str, dict]:
    out = {}
    for p in sorted((root / "f1" / "laps").glob("*.json")):
        out[p.stem] = json.loads(p.read_text())
    return out
