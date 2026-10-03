import { schema, table, t } from 'spacetimedb/server';

// Canonical payloads stay JSON because the Python layer owns Pydantic/domain
// validation. SpacetimeDB owns transaction order, dedupe and subscriptions.
const event = table({ name: 'event', public: true }, {
  eventId: t.string().primaryKey(), sport: t.string().index('btree'), competition: t.string(), season: t.string(),
  startTimeIso: t.string(), status: t.string(), payloadJson: t.string(),
});
const observation = table({ name: 'observation', public: true }, {
  observationId: t.string().primaryKey(), eventId: t.string().index('btree'), sequenceNo: t.u64().index('btree'),
  dedupeKey: t.string().unique(), knownToModelTimeIso: t.string(), payloadJson: t.string(),
});
const stateSnapshot = table({ name: 'state_snapshot', public: true }, {
  snapshotId: t.string().primaryKey(), eventId: t.string().index('btree'), stateVersion: t.u64().index('btree'),
  predictionCutoffIso: t.string(), payloadJson: t.string(),
});
const forecast = table({ name: 'forecast', public: true }, {
  forecastId: t.string().primaryKey(), eventId: t.string().index('btree'), stateVersion: t.u64().index('btree'),
  asOfIso: t.string(), payloadJson: t.string(),
});

// Historical memory / context layer. These tables are deliberately append-only
// except profiles, which are versionable/upsertable identity priors.
const entityProfile = table({ name: 'entity_profile', public: true }, {
  entityId: t.string().primaryKey(), sport: t.string().index('btree'), teamId: t.string().index('btree'),
  updatedAtIso: t.string(), payloadJson: t.string(),
});
const entityMetric = table({ name: 'entity_metric', public: true }, {
  metricId: t.string().primaryKey(), entityId: t.string().index('btree'), knownToModelTimeIso: t.string().index('btree'),
  dedupeKey: t.string().unique(), payloadJson: t.string(),
});
const contextSignal = table({ name: 'context_signal', public: true }, {
  signalId: t.string().primaryKey(), eventId: t.string().index('btree'), knownToModelTimeIso: t.string().index('btree'),
  dedupeKey: t.string().unique(), payloadJson: t.string(),
});
const contextSnapshot = table({ name: 'context_snapshot', public: true }, {
  snapshotId: t.string().primaryKey(), eventId: t.string().index('btree'), stateVersion: t.u64().index('btree'),
  asOfIso: t.string(), payloadJson: t.string(),
});

const spacetimedb = schema({ event, observation, stateSnapshot, forecast, entityProfile, entityMetric, contextSignal, contextSnapshot });
export default spacetimedb;

export const create_event = spacetimedb.reducer(
  { eventId: t.string(), sport: t.string(), competition: t.string(), season: t.string(), startTimeIso: t.string(), status: t.string(), payloadJson: t.string(), stateJson: t.string() },
  (ctx, args) => {
    ctx.db.event.insert({ eventId: args.eventId, sport: args.sport, competition: args.competition, season: args.season, startTimeIso: args.startTimeIso, status: args.status, payloadJson: args.payloadJson });
    ctx.db.stateSnapshot.insert({ snapshotId: `${args.eventId}:0`, eventId: args.eventId, stateVersion: 0n, predictionCutoffIso: args.startTimeIso, payloadJson: args.stateJson });
  }
);
export const append_observation = spacetimedb.reducer(
  { observationId: t.string(), eventId: t.string(), sequenceNo: t.u64(), dedupeKey: t.string(), knownToModelTimeIso: t.string(), payloadJson: t.string() },
  (ctx, args) => ctx.db.observation.insert({ observationId: args.observationId, eventId: args.eventId, sequenceNo: args.sequenceNo, dedupeKey: args.dedupeKey, knownToModelTimeIso: args.knownToModelTimeIso, payloadJson: args.payloadJson })
);
export const commit_state = spacetimedb.reducer(
  { eventId: t.string(), stateVersion: t.u64(), predictionCutoffIso: t.string(), payloadJson: t.string() },
  (ctx, args) => ctx.db.stateSnapshot.insert({ snapshotId: `${args.eventId}:${args.stateVersion}`, eventId: args.eventId, stateVersion: args.stateVersion, predictionCutoffIso: args.predictionCutoffIso, payloadJson: args.payloadJson })
);
export const publish_forecast = spacetimedb.reducer(
  { forecastId: t.string(), eventId: t.string(), stateVersion: t.u64(), asOfIso: t.string(), payloadJson: t.string() },
  (ctx, args) => ctx.db.forecast.insert({ forecastId: args.forecastId, eventId: args.eventId, stateVersion: args.stateVersion, asOfIso: args.asOfIso, payloadJson: args.payloadJson })
);
export const upsert_entity_profile = spacetimedb.reducer(
  { entityId: t.string(), sport: t.string(), teamId: t.string(), updatedAtIso: t.string(), payloadJson: t.string() },
  (ctx, args) => {
    const existing = ctx.db.entityProfile.entityId.find(args.entityId);
    if (existing) ctx.db.entityProfile.entityId.delete(args.entityId);
    ctx.db.entityProfile.insert({ entityId: args.entityId, sport: args.sport, teamId: args.teamId, updatedAtIso: args.updatedAtIso, payloadJson: args.payloadJson });
  }
);
export const append_entity_metric = spacetimedb.reducer(
  { metricId: t.string(), entityId: t.string(), knownToModelTimeIso: t.string(), dedupeKey: t.string(), payloadJson: t.string() },
  (ctx, args) => ctx.db.entityMetric.insert({ metricId: args.metricId, entityId: args.entityId, knownToModelTimeIso: args.knownToModelTimeIso, dedupeKey: args.dedupeKey, payloadJson: args.payloadJson })
);
export const append_context_signal = spacetimedb.reducer(
  { signalId: t.string(), eventId: t.string(), knownToModelTimeIso: t.string(), dedupeKey: t.string(), payloadJson: t.string() },
  (ctx, args) => ctx.db.contextSignal.insert({ signalId: args.signalId, eventId: args.eventId, knownToModelTimeIso: args.knownToModelTimeIso, dedupeKey: args.dedupeKey, payloadJson: args.payloadJson })
);
export const commit_context_snapshot = spacetimedb.reducer(
  { eventId: t.string(), stateVersion: t.u64(), asOfIso: t.string(), payloadJson: t.string() },
  (ctx, args) => ctx.db.contextSnapshot.insert({ snapshotId: `${args.eventId}:${args.stateVersion}`, eventId: args.eventId, stateVersion: args.stateVersion, asOfIso: args.asOfIso, payloadJson: args.payloadJson })
);
