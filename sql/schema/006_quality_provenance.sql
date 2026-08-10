CREATE TABLE IF NOT EXISTS quality_findings (
    finding_id VARCHAR PRIMARY KEY,
    entity_type VARCHAR NOT NULL,
    entity_id VARCHAR NOT NULL,
    finding_code VARCHAR NOT NULL,
    severity VARCHAR NOT NULL,
    details_json JSON,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS provenance (
    provenance_id VARCHAR PRIMARY KEY,
    entity_type VARCHAR NOT NULL,
    entity_id VARCHAR NOT NULL,
    source_id VARCHAR NOT NULL,
    source_snapshot_id VARCHAR NOT NULL,
    source_object_id VARCHAR NOT NULL,
    raw_sha256 VARCHAR NOT NULL,
    adapter_version VARCHAR NOT NULL,
    mapper_version VARCHAR NOT NULL,
    approval_status VARCHAR NOT NULL,
    redistribution_status VARCHAR NOT NULL,
    retrieved_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_findings_entity ON quality_findings(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_provenance_entity ON provenance(entity_type, entity_id);
