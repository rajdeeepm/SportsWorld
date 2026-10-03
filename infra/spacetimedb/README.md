# SportsWorld live world state — SpacetimeDB module

SpacetimeDB is SportsWorld's shared, real-time world state. The Python engine computes every number; this
module holds the canonical *shared copy* that every browser (and agent) subscribes to, so all viewers see the
same versioned season the instant it changes: a final score, a live score, a recomputed season, an injury.

## Tables (all public, read-only to clients)
| table | what it holds |
|---|---|
| `competition` | per league: global state version, season run id, as-of, status, played / remaining / live games |
| `team_odds` | per team: latent strength ± sd, expected wins, qualify / conference / title probabilities |
| `game` | every remaining game: state, live score and clock, SportsWorld win probability, season leverage |
| `world_update` | append-only feed of state changes (finals, availability, recomputes) |
| `win_prob` | append-only live win-probability history per game (survives API restarts) |
| `viewer` | connected clients (maintained by connect / disconnect hooks) |

## Write path
Reducers `publish_competition`, `publish_teams`, `publish_games`, `drop_games`, `add_world_update`,
`add_win_prob` are **owner-only**: `init` records the publishing identity, and any other caller is rejected
with `only the SportsWorld engine can publish world state`. The engine publishes through
`backend/src/sportsworld/live/spacetime_publisher.py`, which diffs and pushes only changed rows every 5 s.

## Run
Hosted: the live database is `sportsworld` on SpacetimeDB **Maincloud** (`wss://maincloud.spacetimedb.com`);
the engine publishes with the owner identity and every visitor of sportsworld.tech subscribes to it.
```
spacetime publish sportsworld --server maincloud   # (owner) deploy the module
# .env: SPACETIMEDB_URL=https://maincloud.spacetimedb.com  SPACETIMEDB_TOKEN=$(spacetime login show --token)
```
Local development:
```
make spacetime          # starts a local server on :3010, publishes the module, regenerates client bindings
# .env: SPACETIMEDB_URL=http://127.0.0.1:3010  SPACETIMEDB_DATABASE=sportsworld  SPACETIMEDB_TOKEN=$(spacetime login show --token)
make live               # API publishes into SpacetimeDB; the frontend subscribes (frontend/src/lib/live.tsx)
```
The frontend falls back to REST polling if SpacetimeDB is unreachable.

`legacy_v12/` holds the earlier per-event scaffold from v1.2 (never deployed).
