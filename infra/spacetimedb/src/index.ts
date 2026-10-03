import { schema, table, t, SenderError, type InferSchema, type ReducerCtx } from 'spacetimedb/server';

// SportsWorld live world state.
// The Python engine owns the models; SpacetimeDB owns the shared, transactional, subscribable world state:
// every browser (and agent) subscribed here sees the same version of every competition the instant it changes.

const config = table(
  { name: 'config', public: false },
  { key: t.string().primaryKey(), owner: t.identity() }
);

const competition = table(
  { name: 'competition', public: true },
  {
    league: t.string().primaryKey(),
    globalStateVersion: t.u64(),
    runId: t.string(),
    asOf: t.string(),
    status: t.string(),
    draws: t.u32(),
    playedGames: t.u32(),
    remainingGames: t.u32(),
    liveGames: t.u32(),
    updatedAt: t.timestamp(),
  }
);

const teamOdds = table(
  { name: 'team_odds', public: true },
  {
    key: t.string().primaryKey(), // league:team_id
    league: t.string().index('btree'),
    teamId: t.string(),
    name: t.string(),
    conference: t.string(),
    rating: t.f64(),
    ratingSd: t.f64(),
    expectedWins: t.f64(),
    qualify: t.f64(),
    conferenceTitle: t.f64(),
    title: t.f64(),
    stateVersion: t.u64(),
  }
);

const game = table(
  { name: 'game', public: true },
  {
    eventId: t.string().primaryKey(),
    league: t.string().index('btree'),
    startTime: t.string(),
    state: t.string(),
    homeId: t.string(),
    awayId: t.string(),
    homeScore: t.u32(),
    awayScore: t.u32(),
    period: t.u32(),
    clockSeconds: t.f64(),
    pHome: t.f64(),
    leverageHome: t.f64(),
    leverageAway: t.f64(),
    stateVersion: t.u64(),
  }
);

const worldUpdate = table(
  { name: 'world_update', public: true },
  {
    id: t.u64().primaryKey().autoInc(),
    league: t.string().index('btree'),
    at: t.string(),
    reason: t.string(),
    teams: t.string(), // comma-separated team ids
    stateVersion: t.u64(),
  }
);

const winProb = table(
  { name: 'win_prob', public: true },
  {
    id: t.u64().primaryKey().autoInc(),
    eventId: t.string().index('btree'),
    at: t.string(),
    pHome: t.f64(),
  }
);

const viewer = table(
  { name: 'viewer', public: true },
  { connectionId: t.connectionId().primaryKey(), connectedAt: t.timestamp() }
);

const spacetimedb = schema({ config, competition, teamOdds, game, worldUpdate, winProb, viewer });
export default spacetimedb;

type Ctx = ReducerCtx<InferSchema<typeof spacetimedb>>;

function requireOwner(ctx: Ctx) {
  const row = ctx.db.config.key.find('owner');
  if (!row) throw new SenderError('module has no owner yet');
  if (!row.owner.equals(ctx.sender)) throw new SenderError('only the SportsWorld engine can publish world state');
}

const TeamRow = t.object('TeamRow', {
  teamId: t.string(), name: t.string(), conference: t.string(), rating: t.f64(), ratingSd: t.f64(),
  expectedWins: t.f64(), qualify: t.f64(), conferenceTitle: t.f64(), title: t.f64(),
});

const GameRow = t.object('GameRow', {
  eventId: t.string(), startTime: t.string(), state: t.string(), homeId: t.string(), awayId: t.string(),
  homeScore: t.u32(), awayScore: t.u32(), period: t.u32(), clockSeconds: t.f64(),
  pHome: t.f64(), leverageHome: t.f64(), leverageAway: t.f64(),
});

const WinProbRow = t.object('WinProbRow', { eventId: t.string(), at: t.string(), pHome: t.f64() });

export const init = spacetimedb.init((ctx) => {
  // the identity that publishes the module is the only writer
  ctx.db.config.insert({ key: 'owner', owner: ctx.sender });
});

export const onConnect = spacetimedb.clientConnected((ctx) => {
  if (ctx.connectionId) ctx.db.viewer.insert({ connectionId: ctx.connectionId, connectedAt: ctx.timestamp });
});

export const onDisconnect = spacetimedb.clientDisconnected((ctx) => {
  if (ctx.connectionId) ctx.db.viewer.connectionId.delete(ctx.connectionId);
});

export const publishCompetition = spacetimedb.reducer(
  {
    league: t.string(), globalStateVersion: t.u64(), runId: t.string(), asOf: t.string(), status: t.string(),
    draws: t.u32(), playedGames: t.u32(), remainingGames: t.u32(), liveGames: t.u32(),
  },
  (ctx, a) => {
    requireOwner(ctx);
    const row = { ...a, updatedAt: ctx.timestamp };
    if (ctx.db.competition.league.find(a.league)) ctx.db.competition.league.update(row);
    else ctx.db.competition.insert(row);
  }
);

export const publishTeams = spacetimedb.reducer(
  { league: t.string(), stateVersion: t.u64(), rows: t.array(TeamRow) },
  (ctx, { league, stateVersion, rows }) => {
    requireOwner(ctx);
    for (const r of rows) {
      const row = { ...r, key: `${league}:${r.teamId}`, league, stateVersion };
      if (ctx.db.teamOdds.key.find(row.key)) ctx.db.teamOdds.key.update(row);
      else ctx.db.teamOdds.insert(row);
    }
  }
);

export const publishGames = spacetimedb.reducer(
  { league: t.string(), stateVersion: t.u64(), rows: t.array(GameRow) },
  (ctx, { league, stateVersion, rows }) => {
    requireOwner(ctx);
    for (const r of rows) {
      const row = { ...r, league, stateVersion };
      if (ctx.db.game.eventId.find(r.eventId)) ctx.db.game.eventId.update(row);
      else ctx.db.game.insert(row);
    }
  }
);

export const dropGames = spacetimedb.reducer(
  { eventIds: t.array(t.string()) },
  (ctx, { eventIds }) => {
    requireOwner(ctx);
    for (const id of eventIds) ctx.db.game.eventId.delete(id);
  }
);

export const addWorldUpdate = spacetimedb.reducer(
  { league: t.string(), at: t.string(), reason: t.string(), teams: t.string(), stateVersion: t.u64() },
  (ctx, a) => {
    requireOwner(ctx);
    ctx.db.worldUpdate.insert({ id: 0n, ...a });
  }
);

export const addWinProb = spacetimedb.reducer(
  { rows: t.array(WinProbRow) },
  (ctx, { rows }) => {
    requireOwner(ctx);
    for (const r of rows) ctx.db.winProb.insert({ id: 0n, ...r });
  }
);
