-- Derived DuckDB projections for Task 12.
-- Raw snapshots, Parquet artifacts, and their manifests remain authoritative.
-- These tables contain no source-only payloads or raw participant names and are
-- rebuildable from authoritative normalized/audit artifacts.

CREATE TABLE IF NOT EXISTS canonical_events (
    event_id VARCHAR PRIMARY KEY,
    source_id VARCHAR NOT NULL,
    source_snapshot_id VARCHAR NOT NULL,
    format VARCHAR,
    name VARCHAR,
    observed_at TIMESTAMPTZ,
    source_status VARCHAR,
    raw_object_id VARCHAR NOT NULL,
    raw_locator VARCHAR NOT NULL,
    raw_sha256 VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS event_deck_observations (
    observation_id VARCHAR PRIMARY KEY,
    event_id VARCHAR NOT NULL,
    canonical_deck_id VARCHAR NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    participant_reference VARCHAR,
    participant_reference_scope VARCHAR NOT NULL,
    final_placement INTEGER,
    aggregate_wins INTEGER NOT NULL,
    aggregate_losses INTEGER NOT NULL,
    aggregate_draws INTEGER NOT NULL,
    source_result_semantics VARCHAR NOT NULL,
    source_id VARCHAR NOT NULL,
    source_snapshot_id VARCHAR NOT NULL,
    raw_object_id VARCHAR NOT NULL,
    raw_locator VARCHAR NOT NULL,
    raw_sha256 VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS canonical_pods (
    pod_id VARCHAR PRIMARY KEY,
    event_id VARCHAR NOT NULL,
    round_number INTEGER NOT NULL,
    occurred_at TIMESTAMPTZ,
    status VARCHAR NOT NULL,
    source_id VARCHAR NOT NULL,
    source_snapshot_id VARCHAR NOT NULL,
    raw_object_id VARCHAR NOT NULL,
    raw_locator VARCHAR NOT NULL,
    raw_sha256 VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS canonical_pod_entries (
    pod_id VARCHAR NOT NULL,
    seat INTEGER NOT NULL,
    event_id VARCHAR NOT NULL,
    round_number INTEGER NOT NULL,
    canonical_deck_id VARCHAR NOT NULL,
    result VARCHAR NOT NULL,
    points DOUBLE,
    placement INTEGER,
    participant_reference VARCHAR,
    participant_reference_scope VARCHAR,
    source_id VARCHAR NOT NULL,
    source_snapshot_id VARCHAR NOT NULL,
    raw_object_id VARCHAR NOT NULL,
    raw_locator VARCHAR NOT NULL,
    raw_sha256 VARCHAR NOT NULL,
    PRIMARY KEY (pod_id, seat)
);

CREATE TABLE IF NOT EXISTS participant_references (
    reference_id VARCHAR PRIMARY KEY,
    scope VARCHAR NOT NULL,
    source_id VARCHAR,
    event_id VARCHAR,
    source_snapshot_id VARCHAR
);

CREATE TABLE IF NOT EXISTS canonical_combos (
    combo_id VARCHAR PRIMARY KEY,
    name VARCHAR,
    required_cards UUID[] NOT NULL,
    optional_cards UUID[] NOT NULL,
    requirements VARCHAR[] NOT NULL,
    results VARCHAR[] NOT NULL,
    steps VARCHAR[] NOT NULL,
    source_status VARCHAR,
    source_id VARCHAR NOT NULL,
    source_snapshot_id VARCHAR NOT NULL,
    raw_object_id VARCHAR NOT NULL,
    raw_locator VARCHAR NOT NULL,
    raw_sha256 VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS canonical_combo_cards (
    combo_id VARCHAR NOT NULL,
    oracle_id UUID NOT NULL,
    role VARCHAR NOT NULL,
    quantity INTEGER NOT NULL,
    source_id VARCHAR NOT NULL,
    source_snapshot_id VARCHAR NOT NULL,
    raw_object_id VARCHAR NOT NULL,
    raw_locator VARCHAR NOT NULL,
    raw_sha256 VARCHAR NOT NULL,
    PRIMARY KEY (combo_id, oracle_id, role)
);

CREATE TABLE IF NOT EXISTS combo_commander_compatibility (
    combo_id VARCHAR NOT NULL,
    commander_oracle_id UUID NOT NULL,
    compatible BOOLEAN NOT NULL,
    source_id VARCHAR NOT NULL,
    source_snapshot_id VARCHAR NOT NULL,
    raw_object_id VARCHAR NOT NULL,
    raw_locator VARCHAR NOT NULL,
    raw_sha256 VARCHAR NOT NULL,
    PRIMARY KEY (combo_id, commander_oracle_id)
);

CREATE INDEX IF NOT EXISTS idx_event_observations_event
    ON event_deck_observations(event_id);
CREATE INDEX IF NOT EXISTS idx_canonical_pods_event
    ON canonical_pods(event_id);
CREATE INDEX IF NOT EXISTS idx_canonical_pod_entries_deck
    ON canonical_pod_entries(canonical_deck_id);
CREATE INDEX IF NOT EXISTS idx_canonical_combo_cards_oracle
    ON canonical_combo_cards(oracle_id);
