CREATE TABLE IF NOT EXISTS events (
  event_id text PRIMARY KEY,
  sport text NOT NULL,
  competition text NOT NULL,
  season text NOT NULL,
  participants jsonb NOT NULL DEFAULT '[]'::jsonb,
  venue text,
  start_time timestamptz NOT NULL,
  status text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS observations (
  observation_id uuid PRIMARY KEY,
  event_id text NOT NULL REFERENCES events(event_id),
  sport text NOT NULL,
  kind text NOT NULL,
  payload_json jsonb NOT NULL,
  source_id text NOT NULL,
  source_type text NOT NULL,
  source_url_or_ref text,
  confidence double precision NOT NULL CHECK(confidence BETWEEN 0 AND 1),
  event_time timestamptz,
  known_to_model_time timestamptz NOT NULL,
  ingestion_time timestamptz NOT NULL,
  sequence_no integer NOT NULL,
  dedupe_key text NOT NULL,
  parser_version text,
  raw_record_ref text,
  verified boolean NOT NULL,
  UNIQUE(event_id,dedupe_key)
);
CREATE INDEX IF NOT EXISTS observations_event_seq ON observations(event_id,sequence_no);
CREATE INDEX IF NOT EXISTS observations_known_time ON observations(event_id,known_to_model_time);
CREATE TABLE IF NOT EXISTS state_snapshots (
  event_id text NOT NULL REFERENCES events(event_id),
  state_version integer NOT NULL,
  as_of timestamptz NOT NULL,
  features_json jsonb NOT NULL,
  observation_cursor integer NOT NULL,
  prediction_cutoff timestamptz NOT NULL,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY(event_id,state_version)
);
CREATE TABLE IF NOT EXISTS forecasts (
  forecast_id uuid PRIMARY KEY,
  event_id text NOT NULL REFERENCES events(event_id),
  state_version integer NOT NULL,
  model_version text NOT NULL,
  calibration_version text NOT NULL,
  as_of timestamptz NOT NULL,
  data_cutoff timestamptz NOT NULL,
  payload_json jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS forecasts_event_asof ON forecasts(event_id,as_of);
CREATE TABLE IF NOT EXISTS counterfactual_runs (
  run_id uuid PRIMARY KEY,
  event_id text NOT NULL REFERENCES events(event_id),
  base_state_version integer NOT NULL,
  overrides_json jsonb NOT NULL,
  draws integer NOT NULL,
  seed integer NOT NULL,
  payload_json jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS feature_snapshots (
  event_id text NOT NULL,
  prediction_time timestamptz NOT NULL,
  schema_version text NOT NULL,
  features_json jsonb NOT NULL,
  target jsonb,
  max_known_to_model_time timestamptz NOT NULL,
  PRIMARY KEY(event_id,prediction_time,schema_version),
  CHECK(max_known_to_model_time <= prediction_time)
);
CREATE TABLE IF NOT EXISTS model_registry (
  model_version text PRIMARY KEY,
  sport text NOT NULL,
  algorithm text NOT NULL,
  feature_schema text NOT NULL,
  train_window jsonb NOT NULL,
  calibration_window jsonb NOT NULL,
  test_window jsonb NOT NULL,
  artifact_uri text NOT NULL,
  calibration_version text NOT NULL,
  metrics_json jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS backtest_runs (
  run_id text PRIMARY KEY,
  sport text NOT NULL,
  model_version text NOT NULL,
  split_spec jsonb NOT NULL,
  metrics_json jsonb NOT NULL,
  payload_json jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS data_sources (
  source_id text PRIMARY KEY,
  type text NOT NULL,
  provider text NOT NULL,
  trust_level text NOT NULL,
  parser_version text NOT NULL,
  enabled boolean NOT NULL DEFAULT true
);

-- Historical memory / latent entity state -------------------------------------
CREATE TABLE IF NOT EXISTS entity_profiles (
  entity_id text PRIMARY KEY,
  sport text NOT NULL,
  entity_type text NOT NULL,
  display_name text NOT NULL,
  team_id text,
  role text,
  attributes_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  capabilities_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  importance double precision NOT NULL DEFAULT 0.5 CHECK(importance BETWEEN 0 AND 1),
  source_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  valid_from timestamptz,
  valid_to timestamptz,
  updated_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS entity_profiles_sport_team ON entity_profiles(sport,team_id);

CREATE TABLE IF NOT EXISTS entity_metrics (
  metric_id uuid PRIMARY KEY,
  entity_id text NOT NULL REFERENCES entity_profiles(entity_id),
  sport text NOT NULL,
  metric text NOT NULL,
  dimension text NOT NULL,
  raw_value_json jsonb NOT NULL,
  normalized_value double precision NOT NULL CHECK(normalized_value BETWEEN -1 AND 1),
  unit text,
  sample_size double precision NOT NULL DEFAULT 1 CHECK(sample_size >= 0),
  occurred_at timestamptz NOT NULL,
  known_to_model_time timestamptz NOT NULL,
  ingestion_time timestamptz NOT NULL,
  source_id text NOT NULL,
  source_type text NOT NULL,
  source_url_or_ref text,
  confidence double precision NOT NULL CHECK(confidence BETWEEN 0 AND 1),
  event_id text,
  opponent_id text,
  season text,
  competition text,
  tags_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  dedupe_key text NOT NULL,
  UNIQUE(entity_id,dedupe_key)
);
CREATE INDEX IF NOT EXISTS entity_metrics_entity_time ON entity_metrics(entity_id,known_to_model_time);
CREATE INDEX IF NOT EXISTS entity_metrics_dimension ON entity_metrics(entity_id,dimension,known_to_model_time);

CREATE TABLE IF NOT EXISTS context_signals (
  signal_id uuid PRIMARY KEY,
  event_id text NOT NULL,
  sport text NOT NULL,
  category text NOT NULL,
  effect text NOT NULL,
  label text NOT NULL,
  summary text NOT NULL,
  target_entity_id text,
  direction double precision NOT NULL CHECK(direction BETWEEN -1 AND 1),
  strength double precision NOT NULL CHECK(strength BETWEEN 0 AND 1),
  volatility double precision NOT NULL CHECK(volatility BETWEEN 0 AND 1),
  sentiment text NOT NULL,
  observed_at timestamptz NOT NULL,
  known_to_model_time timestamptz NOT NULL,
  ingestion_time timestamptz NOT NULL,
  source_id text NOT NULL,
  source_type text NOT NULL,
  source_url_or_ref text,
  confidence double precision NOT NULL CHECK(confidence BETWEEN 0 AND 1),
  verified boolean NOT NULL,
  public_evidence_only boolean NOT NULL DEFAULT true,
  parser_version text,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  dedupe_key text NOT NULL,
  UNIQUE(event_id,dedupe_key)
);
CREATE INDEX IF NOT EXISTS context_signals_event_time ON context_signals(event_id,known_to_model_time);

CREATE TABLE IF NOT EXISTS context_snapshots (
  event_id text NOT NULL REFERENCES events(event_id),
  state_version integer NOT NULL,
  as_of timestamptz NOT NULL,
  payload_json jsonb NOT NULL,
  PRIMARY KEY(event_id,state_version)
);
