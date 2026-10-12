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
    "SEASON_BATCH_DRAWS": "128",
    "FRONTEND_ORIGIN": "https://worldofsports.tech",
    "REAL_DATA_DIR": str(root / "data" / "real"),
    "PYTHONUNBUFFERED": "1",
}
for key, value in defaults.items():
    os.environ.setdefault(key, value)
os.execv(sys.executable, [sys.executable, "-m", "uvicorn", "sportsworld.api.main:app",
                         "--host", "0.0.0.0", "--port", os.environ.get("PORT", "10000"),
                         "--workers", "1"])
