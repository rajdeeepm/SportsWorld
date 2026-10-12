"""Bounded, ephemeral private simulation jobs for a single cloud instance."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import threading
import time
from typing import Callable
from uuid import uuid4

from fastapi import HTTPException


@dataclass
class Job:
    created: float
    done_at: float | None = None
    result: object = None
    error: HTTPException | None = None


class SimulationJobs:
    def __init__(self, max_pending: int = 4, max_records: int = 8, ttl: float = 600):
        self.max_pending, self.max_records, self.ttl = max_pending, max_records, ttl
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="private-simulation")
        self.lock = threading.Lock()
        self.jobs: dict[str, Job] = {}

    def _prune(self):
        now = time.monotonic()
        for key, job in list(self.jobs.items()):
            if job.done_at is not None and now - job.done_at > self.ttl:
                del self.jobs[key]
        while len(self.jobs) >= self.max_records:
            finished = [(j.done_at, k) for k, j in self.jobs.items() if j.done_at is not None]
            if not finished:
                break
            del self.jobs[min(finished)[1]]

    def submit(self, operation: Callable):
        with self.lock:
            self._prune()
            if sum(j.done_at is None for j in self.jobs.values()) >= self.max_pending:
                raise HTTPException(429, "Simulation queue is full; try again shortly", headers={"Retry-After": "10"})
            key = uuid4().hex
            job = self.jobs[key] = Job(time.monotonic())

        def run():
            try:
                result, error = operation(), None
            except HTTPException as exc:
                result, error = None, exc
            except Exception:
                result, error = None, HTTPException(500, "Simulation failed; please retry")
            with self.lock:
                job.result, job.error, job.done_at = result, error, time.monotonic()
        self.pool.submit(run)
        return key

    def get(self, key: str):
        with self.lock:
            job = self.jobs.get(key)
            if job is None or (job.done_at is not None and time.monotonic() - job.done_at > self.ttl):
                self.jobs.pop(key, None)
                raise HTTPException(404, "Simulation result expired; run the scenario again")
            if job.done_at is None:
                return False, None
            if job.error is not None:
                raise job.error
            return True, job.result


simulation_jobs = SimulationJobs()
