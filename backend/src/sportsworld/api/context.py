from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sportsworld.config import Settings
from sportsworld.core.engine import ForecastEngine
from sportsworld.context import ContextEngine
from sportsworld.core.replay import ReplayManager
from sportsworld.core.simulation import Simulator
from sportsworld.models.registry import ModelRegistry
from sportsworld.sports import BasketballAdapter,F1Adapter,FootballAdapter,HockeyAdapter
from sportsworld.schemas import Sport
from sportsworld.stores import MemoryStore,PostgresStore,SpacetimeDBStore
from sportsworld.llm.scenario import ScenarioParser
from sportsworld.voice import ElevenLabsVoice
from .ws import WebSocketHub


@dataclass
class AppContext:
    settings:Settings
    hub:WebSocketHub
    store:object
    engine:ForecastEngine
    simulator:Simulator
    replay:ReplayManager
    scenario_parser:ScenarioParser
    voice:ElevenLabsVoice
    registry:ModelRegistry
    context_engine:ContextEngine


def build_context(settings:Settings)->AppContext:
    adapters={Sport.FOOTBALL:FootballAdapter(),Sport.BASKETBALL:BasketballAdapter(),Sport.F1:F1Adapter(),Sport.HOCKEY:HockeyAdapter()}
    if settings.store_backend=='postgres':
        if not settings.database_url: raise RuntimeError('DATABASE_URL required')
        store=PostgresStore(settings.database_url)
    elif settings.store_backend=='spacetimedb':
        if not settings.spacetimedb_url: raise RuntimeError('SPACETIMEDB_URL required')
        store=SpacetimeDBStore(settings.spacetimedb_url,settings.spacetimedb_token)
    else: store=MemoryStore()
    hub=WebSocketHub(); registry=ModelRegistry(settings,adapters); context_engine=ContextEngine(store); engine=ForecastEngine(store,adapters,registry,context_engine=context_engine,publish=hub.publish_sync); simulator=Simulator(adapters,registry,context_engine)
    repo=Path(__file__).resolve().parents[4]; replay_dir=repo/'data'/'replays'; replay=ReplayManager(engine,replay_dir,notify=hub.publish_sync)
    return AppContext(settings,hub,store,engine,simulator,replay,ScenarioParser(settings),ElevenLabsVoice(settings),registry,context_engine)
