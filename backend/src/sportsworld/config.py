from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    sportsworld_env: str = "local"
    store_backend: str = "memory"  # memory | postgres | spacetimedb
    database_url: str | None = None
    spacetimedb_url: str | None = None
    spacetimedb_token: str | None = None
    spacetimedb_database: str = "sportsworld"
    model_artifact_bucket: str | None = None
    aws_region: str = "us-east-2"
    llm_provider: str = "deterministic"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str = "meta-llama/Llama-3.3-70B-Instruct"
    elevenlabs_api_key: str | None = None
    elevenlabs_voice_id: str | None = None
    admin_api_token: str | None = None
    frontend_origin: str = "http://localhost:5173"
    replay_seed: int = 7
    model_dir: Path = Path("../models/artifacts")
    manifest_dir: Path = Path("../models/manifests")
    backtest_dir: Path = Path("../data/fixtures/backtests")
    replay_dir: Path = Path("../data/replays")
    source_timeout_seconds: float = 5.0
    # Real-world league tracking (every team, every game).
    tracker_enabled: bool = False
    tracker_leagues: str = ""  # comma-separated league ids; empty = all ESPN-backed leagues
    tracker_schedule_interval: float = 600.0
    tracker_live_interval: float = 20.0
    real_data_dir: Path = Path("../data/real")
    openf1_token: str | None = None
    season_engine: bool = True
    season_as_of: str | None = None  # ISO time: rebuild every competition as it stood then (offline replay, no network)
    season_sim_draws: int = 10_000

    @property
    def is_demo(self) -> bool:
        return self.sportsworld_env in {"demo", "local"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
