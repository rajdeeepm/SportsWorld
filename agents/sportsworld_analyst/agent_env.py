"""Read a setting from the environment or the repo's .env (secrets stay out of code and git)."""
from __future__ import annotations

import os
from pathlib import Path

_ENV = Path(__file__).resolve().parents[2] / ".env"


def env(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    if _ENV.exists():
        for line in _ENV.read_text().splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"')
    return None
