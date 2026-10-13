"""Small, credential-free resource samples for the single cloud container."""
import json
import logging
import os
from pathlib import Path
import resource
import sys


def memory_sample() -> dict:
    sample = {"pid": os.getpid()}
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    sample["peak_rss_mb"] = round(peak / (1024 * 1024 if sys.platform == "darwin" else 1024), 2)
    if sys.platform.startswith("linux"):
        try:
            status = Path("/proc/self/status").read_text()
            sample["rss_mb"] = round(int(next(line.split()[1] for line in status.splitlines()
                                               if line.startswith("VmRSS:"))) / 1024, 2)
            root = Path("/sys/fs/cgroup")
            for name, filename in (("container_mb", "memory.current"), ("limit_mb", "memory.max")):
                value = (root / filename).read_text().strip()
                if value.isdigit():
                    sample[name] = round(int(value) / 1024**2, 2)
            stats = dict(line.split() for line in (root / "memory.stat").read_text().splitlines())
            for key in ("anon", "file", "shmem"):
                sample[key + "_mb"] = round(int(stats.get(key, 0)) / 1024**2, 2)
        except (OSError, StopIteration, ValueError):
            pass
    return sample


def log_memory(phase: str, league: str | None = None) -> None:
    if os.environ.get("SPORTSWORLD_RESOURCE_LOG") == "1":
        logging.getLogger("uvicorn.error").info("memory %s", json.dumps({"phase": phase, "league": league, **memory_sample()}))
