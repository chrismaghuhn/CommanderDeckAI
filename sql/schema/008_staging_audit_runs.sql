-- Task 5 derived local indexes for staging, audit, provenance, runs, and normalized manifests.
-- Raw objects, Parquet tables, and versioned manifests remain authoritative.
CREATE TABLE IF NOT EXISTS staging_records (
    staging_record_id VARCHAR PRIMARY KEY,
    source_id VARCHAR NOT NULL,
    source_snapshot_id VARCHAR NOT NULL,
    raw_object_id VARCHAR NOT NULL,
    raw_object_path VARCHAR NOT NULL,
    raw_locator_json JSON NOT NULL,
    record_type VARCHAR NOT NULL,
    original_source_values_json JSON NOT NULL,
    status VARCHAR NOT NULL CHECK (status IN ('OBSERVED', 'INCOMPLETE', 'PARSE_FAILED', 'STRUCTURAL_INVALID')),
    finding_codes_json JSON NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_records (
    audit_id VARCHAR PRIMARY KEY,
    entity_id VARCHAR NOT NULL,
    stage VARCHAR NOT NULL CHECK (stage IN ('parse', 'integrity', 'resolution', 'legality', 'quality')),
    finding_code VARCHAR NOT NULL,
    raw_locator_json JSON,
    details_json JSON NOT NULL,
    layer VARCHAR NOT NULL CHECK (layer = 'audit')
);

CREATE TABLE IF NOT EXISTS resolution_attempts (
    attempt_id VARCHAR PRIMARY KEY,
    staging_record_id VARCHAR NOT NULL,
    raw_locator_json JSON NOT NULL,
    source_field VARCHAR NOT NULL,
    original_source_value_json JSON NOT NULL,
    resolver_version VARCHAR NOT NULL,
    normalization_policy_version VARCHAR NOT NULL,
    alias_catalog_version VARCHAR NOT NULL,
    card_catalog_snapshot_id VARCHAR NOT NULL,
    status VARCHAR NOT NULL CHECK (status IN ('RESOLVED', 'AMBIGUOUS', 'UNRESOLVED')),
    candidate_canonical_ids_json JSON NOT NULL,
    canonical_id VARCHAR,
    finding_codes_json JSON NOT NULL,
    attempted_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS quarantine_records (
    quarantine_id VARCHAR PRIMARY KEY,
    staging_record_id VARCHAR NOT NULL,
    reason_code VARCHAR NOT NULL,
    raw_locator_json JSON NOT NULL,
    original_source_values_json JSON NOT NULL,
    layer VARCHAR NOT NULL CHECK (layer = 'quarantine')
);

CREATE TABLE IF NOT EXISTS run_manifests (
    run_id VARCHAR PRIMARY KEY,
    run_kind VARCHAR NOT NULL,
    stage VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    manifest_path VARCHAR NOT NULL,
    manifest_sha256 VARCHAR NOT NULL,
    git_commit VARCHAR NOT NULL,
    dependency_lock_hash VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    finished_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS run_inputs (
    run_id VARCHAR NOT NULL,
    kind VARCHAR NOT NULL,
    input_id VARCHAR NOT NULL,
    path VARCHAR,
    sha256 VARCHAR NOT NULL,
    PRIMARY KEY (run_id, kind, input_id)
);

CREATE TABLE IF NOT EXISTS run_artifacts (
    run_id VARCHAR NOT NULL,
    kind VARCHAR NOT NULL,
    path VARCHAR NOT NULL,
    sha256 VARCHAR NOT NULL,
    PRIMARY KEY (run_id, path)
);

CREATE TABLE IF NOT EXISTS normalized_snapshot_manifests (
    normalized_snapshot_id VARCHAR PRIMARY KEY,
    producing_run_id VARCHAR NOT NULL,
    source_id VARCHAR NOT NULL,
    input_source_snapshot_manifest_id VARCHAR NOT NULL,
    input_source_snapshot_manifest_sha256 VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    manifest_path VARCHAR NOT NULL,
    manifest_sha256 VARCHAR NOT NULL,
    normalized_content_sha256 VARCHAR NOT NULL,
    counts_json JSON NOT NULL,
    finding_codes_json JSON NOT NULL,
    quarantine_references_json JSON NOT NULL,
    created_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS normalized_snapshot_artifacts (
    normalized_snapshot_id VARCHAR NOT NULL,
    layer VARCHAR NOT NULL CHECK (layer IN ('normalized', 'audit', 'quarantine')),
    table_name VARCHAR NOT NULL,
    path VARCHAR NOT NULL,
    sha256 VARCHAR NOT NULL,
    row_count BIGINT NOT NULL CHECK (row_count >= 0),
    byte_count BIGINT NOT NULL CHECK (byte_count >= 0),
    PRIMARY KEY (normalized_snapshot_id, layer)
);

CREATE INDEX IF NOT EXISTS idx_staging_source_snapshot
    ON staging_records(source_id, source_snapshot_id);
CREATE INDEX IF NOT EXISTS idx_audit_stage_code
    ON audit_records(stage, finding_code);
CREATE INDEX IF NOT EXISTS idx_resolution_staging
    ON resolution_attempts(staging_record_id);
CREATE INDEX IF NOT EXISTS idx_quarantine_reason
    ON quarantine_records(reason_code);
CREATE INDEX IF NOT EXISTS idx_normalized_source
    ON normalized_snapshot_manifests(source_id, input_source_snapshot_manifest_id);
CREATE INDEX IF NOT EXISTS idx_run_inputs_hash
    ON run_inputs(sha256);
CREATE INDEX IF NOT EXISTS idx_run_artifacts_hash
    ON run_artifacts(sha256);
