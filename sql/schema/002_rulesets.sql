CREATE TABLE IF NOT EXISTS rulesets (
    ruleset_version VARCHAR PRIMARY KEY,
    format VARCHAR NOT NULL,
    effective_from DATE NOT NULL,
    effective_until DATE,
    required_total_cards INTEGER NOT NULL,
    default_copy_limit INTEGER NOT NULL,
    command_zone_min INTEGER NOT NULL,
    command_zone_max INTEGER NOT NULL,
    validator_version VARCHAR NOT NULL,
    manifest_sha256 VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS ruleset_bans (
    ruleset_version VARCHAR NOT NULL,
    oracle_id UUID NOT NULL,
    ban_scope VARCHAR NOT NULL,
    PRIMARY KEY (ruleset_version, oracle_id, ban_scope)
);

CREATE TABLE IF NOT EXISTS ruleset_copy_overrides (
    ruleset_version VARCHAR NOT NULL,
    oracle_id UUID NOT NULL,
    copy_limit INTEGER,
    unlimited BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (ruleset_version, oracle_id)
);
