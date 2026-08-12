-- Derived local cache for verified raw snapshots.
-- Raw objects and manifests remain the authoritative, rebuildable source.
CREATE TABLE IF NOT EXISTS source_snapshot_manifests (
    source_id VARCHAR NOT NULL,
    source_snapshot_id VARCHAR NOT NULL,
    status VARCHAR NOT NULL CHECK (status IN ('COMPLETE', 'INCOMPLETE', 'FAILED')),
    approval_status VARCHAR NOT NULL,
    adapter_version VARCHAR NOT NULL,
    usage_status VARCHAR NOT NULL,
    attribution_required BOOLEAN NOT NULL,
    redistribution_status VARCHAR NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    manifest_path VARCHAR NOT NULL,
    manifest_sha256 VARCHAR,
    snapshot_content_sha256 VARCHAR NOT NULL,
    PRIMARY KEY (source_id, source_snapshot_id)
);

CREATE TABLE IF NOT EXISTS snapshot_requests (
    source_id VARCHAR NOT NULL,
    source_snapshot_id VARCHAR NOT NULL,
    request_id VARCHAR NOT NULL,
    sanitized_method VARCHAR NOT NULL,
    sanitized_endpoint VARCHAR NOT NULL,
    api_version VARCHAR,
    format VARCHAR,
    sanitized_parameters JSON NOT NULL,
    PRIMARY KEY (source_id, source_snapshot_id, request_id)
);

CREATE TABLE IF NOT EXISTS snapshot_objects (
    source_id VARCHAR NOT NULL,
    source_snapshot_id VARCHAR NOT NULL,
    raw_object_id VARCHAR NOT NULL,
    request_id VARCHAR NOT NULL,
    source_object_id VARCHAR,
    retrieved_at TIMESTAMP NOT NULL,
    path VARCHAR NOT NULL,
    byte_count BIGINT NOT NULL CHECK (byte_count >= 0),
    content_type VARCHAR,
    sha256 VARCHAR NOT NULL,
    upstream_sha256 VARCHAR,
    checksum_verification_status VARCHAR NOT NULL,
    logical_record_count BIGINT CHECK (logical_record_count IS NULL OR logical_record_count >= 0),
    PRIMARY KEY (source_id, source_snapshot_id, raw_object_id)
);

CREATE INDEX IF NOT EXISTS idx_snapshot_manifests_status
    ON source_snapshot_manifests(status);
CREATE INDEX IF NOT EXISTS idx_snapshot_requests_endpoint
    ON snapshot_requests(sanitized_endpoint);
CREATE INDEX IF NOT EXISTS idx_snapshot_objects_request
    ON snapshot_objects(source_id, source_snapshot_id, request_id);
CREATE INDEX IF NOT EXISTS idx_snapshot_objects_digest
    ON snapshot_objects(sha256);
