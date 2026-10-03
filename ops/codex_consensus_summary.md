Created [scripts/external_consensus.py](scripts/external_consensus.py). It replays point-in-time ratings, scores pregame forecasts, caches ESPN odds, and calculates the paired metrics and research-only A6 blend. Parser and metric checks passed.

The requested command completed, but ESPN’s odds hostname failed DNS resolution in this workspace. The reports were written with **no paired games**, so log loss and the other comparison metrics cannot be reported:

| League | Eligible games selected | Paired games |
|---|---:|---:|
| NFL | 569 | 0 |
| NBA | 1,500 | 0 |
| NHL | 1,500 | 0 |

The [NFL](data/fixtures/backtests/consensus_nfl.json), [NBA](data/fixtures/backtests/consensus_nba.json), and [NHL](data/fixtures/backtests/consensus_nhl.json) reports mark this as `no_paired_games`. Rerunning the same command where ESPN is reachable will fetch and cache odds, then produce the summary metrics.