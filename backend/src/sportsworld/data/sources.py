from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DataSource:
    source_id: str
    source_type: str
    provider: str
    trust_level: str
    parser_version: str
    enabled: bool = True
    purpose: str = "live"


DEFAULT_SOURCES = [
    DataSource('replay-stats','stats','SportsWorld replay','verified','replay-v1',purpose='live play-by-play / box score'),
    DataSource('replay-weather','weather','SportsWorld replay','verified','replay-v1',purpose='event environment'),
    DataSource('replay-timing','telemetry','SportsWorld replay','verified','replay-v1',purpose='F1 live timing / telemetry'),
    DataSource('official-team-report','official','Official team report','verified','schema-v1',purpose='availability / roster / public context'),
    DataSource('espn-scoreboard','stats','ESPN public scoreboard API (unofficial)','public-unofficial','espn-scoreboard-v1',purpose='every game/team: schedule, live score/clock/situation, results (NFL, FBS, NBA, WNBA, NCAA D-I M/W)'),
    DataSource('espn-summary','stats','ESPN public game summary API (unofficial)','public-unofficial','espn-pbp-v1',purpose='football play-by-play for training; ESPN win probability kept as external comparator only'),
    DataSource('jolpica-f1','official','Jolpica F1 (Ergast-compatible)','public','f1-v1',purpose='F1 calendar, qualifying grid, classified results'),
    DataSource('openf1-timing','telemetry','OpenF1','public','f1-v1',purpose='F1 lap timing, running order, gaps, safety car, rainfall'),
    DataSource('synthetic-history','stats','SportsWorld synthetic historical fixture','demo-only','context-v2',purpose='career / season / recent-form historical memory'),
    DataSource('synthetic-context','news','SportsWorld synthetic contextual fixture','demo-only','context-v2',purpose='public narrative / rivalry / rest / environment context'),
    DataSource('synthetic-official','official','SportsWorld synthetic official-style fixture','demo-only','context-v2',purpose='public availability context'),
]
