from __future__ import annotations

from datetime import datetime,timezone
from pathlib import Path
import pytest
from sportsworld.config import Settings
from sportsworld.api.context import build_context
from sportsworld.schemas import EventCreate,Sport

@pytest.fixture
def ctx(tmp_path):
    settings=Settings(sportsworld_env='test',store_backend='memory',model_dir=Path('unused'),manifest_dir=Path('unused'))
    c=build_context(settings)
    req=EventCreate(event_id='test-game',sport=Sport.FOOTBALL,competition='test',season='2026',outcomes=['home','away'],start_time=datetime(2026,1,1,tzinfo=timezone.utc),participants=['Home','Away'],initial_features={'home_strength':.2,'away_strength':.1})
    c.engine.create_event(req)
    return c
