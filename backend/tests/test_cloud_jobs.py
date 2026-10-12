import threading

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sportsworld.api import season_routes
from sportsworld.api.jobs import SimulationJobs


def test_cloud_submission_does_not_block_http_and_preserves_result_contract(monkeypatch):
    gate = threading.Event()
    jobs = SimulationJobs(max_pending=1)

    class Service:
        def scenario(self, *args, **kwargs):
            assert gate.wait(3)
            return {"base": {"teams": [], "games": []}, "scenario": {"teams": [], "games": []}, "deltas": []}

    monkeypatch.setenv("SEASON_ASYNC_JOBS", "1")
    monkeypatch.setattr(season_routes, "simulation_jobs", jobs)
    monkeypatch.setattr(season_routes, "_service", Service())
    monkeypatch.setattr(season_routes, "_limiter_dep", None)
    app = FastAPI()
    app.include_router(season_routes.router)
    try:
        with TestClient(app) as client:
            submitted = client.post("/competitions/nfl/seasons/current/season-simulations", json={})
            assert submitted.status_code == 202
            assert submitted.headers["cache-control"] == "no-store"
            poll = submitted.json()["poll"]
            assert client.get(poll).status_code == 202
            blocked = client.post("/competitions/nfl/seasons/current/season-simulations", json={})
            assert blocked.status_code == 429 and blocked.headers["retry-after"] == "10"
            gate.set()
            jobs.pool.shutdown(wait=True)
            completed = client.get(poll)
            assert completed.status_code == 200
            assert completed.json()["base"] == {"teams": []}
            assert completed.json()["scenario"] == {"teams": []}
            assert completed.json()["deltas"] == []
            assert client.get("/simulation-jobs/unknown").status_code == 404
    finally:
        gate.set()
        jobs.pool.shutdown(wait=True)
