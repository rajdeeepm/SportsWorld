"""Run the original API and its tracking/simulation workers on one cloud instance."""
from pathlib import Path
import os
import sys

root = Path(__file__).resolve().parents[1]
os.chdir(root)
defaults = {
    "SPORTSWORLD_ENV": "production",
    "TRACKER_ENABLED": "true",
    "TRACKER_LEAGUES": "nfl,college-football,nba,mens-college-basketball,nhl,mens-college-hockey,f1",
    "SEASON_ENGINE": "true",
    "SEASON_BATCH_DRAWS": "256",
    "SEASON_WORKER_PROCESS": "1",
    "SEASON_ASYNC_JOBS": "1",
    "FRONTEND_ORIGIN": "https://worldofsports.tech",
    "SPORTSWORLD_API": "http://127.0.0.1:" + os.environ.get("PORT", "10000"),
    "REAL_DATA_DIR": str(root / "data" / "real"),
    "PYTHONUNBUFFERED": "1",
    "PYTHONMALLOC": "malloc",
    "MALLOC_ARENA_MAX": "2",
    "OPENBLAS_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
}
for key, value in defaults.items():
    os.environ.setdefault(key, value)
for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[key] = "1"
os.execv(sys.executable, [sys.executable, "-m", "uvicorn", "sportsworld.api.main:app",
                         "--host", "0.0.0.0", "--port", os.environ.get("PORT", "10000"),
                         "--workers", "1"])
