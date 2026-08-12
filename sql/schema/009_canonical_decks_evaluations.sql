-- Derived local query/index/cache tables for canonical deck evaluation.
-- Canonical Parquet artifacts and versioned manifests remain authoritative.
CREATE TABLE IF NOT EXISTS canonical_decks (
    canonical_deck_id CHAR(64) PRIMARY KEY,
    structural_fingerprint CHAR(64) NOT NULL,
    fingerprint_algorithm_version VARCHAR NOT NULL,
    format VARCHAR NOT NULL,
    command_zone_json JSON NOT NULL,
    card_zones_json JSON NOT NULL,
    provenance_json JSON NOT NULL
);

CREATE TABLE IF NOT EXISTS deck_legality_evaluations (
    canonical_deck_id CHAR(64) NOT NULL,
    ruleset_version VARCHAR NOT NULL,
    evaluated_at TIMESTAMP NOT NULL,
    ruleset_snapshot_sha256 CHAR(64),
    validator_version VARCHAR NOT NULL,
    legal_status VARCHAR NOT NULL,
    finding_codes_json JSON NOT NULL,
    provenance_json JSON NOT NULL,
    PRIMARY KEY (canonical_deck_id, ruleset_version, evaluated_at)
);

CREATE TABLE IF NOT EXISTS deck_quality_evaluations (
    canonical_deck_id CHAR(64) NOT NULL,
    evaluated_at TIMESTAMP NOT NULL,
    evaluator_version VARCHAR NOT NULL,
    quality_status VARCHAR NOT NULL,
    finding_codes_json JSON NOT NULL,
    metrics_json JSON NOT NULL,
    quarantine_references_json JSON NOT NULL,
    provenance_json JSON NOT NULL,
    PRIMARY KEY (canonical_deck_id, evaluated_at, evaluator_version)
);

CREATE TABLE IF NOT EXISTS deck_deduplication_groups (
    group_id VARCHAR NOT NULL,
    group_kind VARCHAR NOT NULL,
    algorithm_version VARCHAR NOT NULL,
    threshold DOUBLE,
    canonical_deck_id CHAR(64) NOT NULL,
    source_id VARCHAR,
    source_deck_id VARCHAR,
    PRIMARY KEY (group_id, canonical_deck_id)
);

CREATE INDEX IF NOT EXISTS idx_canonical_decks_fingerprint
    ON canonical_decks(structural_fingerprint);
CREATE INDEX IF NOT EXISTS idx_legality_deck
    ON deck_legality_evaluations(canonical_deck_id);
CREATE INDEX IF NOT EXISTS idx_quality_deck
    ON deck_quality_evaluations(canonical_deck_id);
CREATE INDEX IF NOT EXISTS idx_dedup_group_kind
    ON deck_deduplication_groups(group_kind, algorithm_version);
