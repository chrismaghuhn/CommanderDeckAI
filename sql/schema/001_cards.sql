CREATE TABLE IF NOT EXISTS cards (
    card_snapshot_id VARCHAR NOT NULL,
    oracle_id UUID NOT NULL,
    name VARCHAR NOT NULL,
    normalized_name VARCHAR NOT NULL,
    layout VARCHAR NOT NULL,
    mana_value DOUBLE NOT NULL,
    mana_cost VARCHAR,
    colors VARCHAR[] NOT NULL,
    color_identity VARCHAR[] NOT NULL,
    supertypes VARCHAR[] NOT NULL,
    types VARCHAR[] NOT NULL,
    subtypes VARCHAR[] NOT NULL,
    keywords VARCHAR[] NOT NULL,
    oracle_text VARCHAR,
    commander_legality VARCHAR NOT NULL,
    copy_limit_policy VARCHAR NOT NULL,
    fixed_copy_limit INTEGER,
    is_basic_land BOOLEAN NOT NULL,
    is_token BOOLEAN NOT NULL,
    is_digital BOOLEAN NOT NULL,
    released_at DATE,
    PRIMARY KEY (card_snapshot_id, oracle_id)
);

CREATE TABLE IF NOT EXISTS printings (
    card_snapshot_id VARCHAR NOT NULL,
    printing_id UUID NOT NULL,
    oracle_id UUID NOT NULL,
    source VARCHAR NOT NULL,
    set_code VARCHAR,
    collector_number VARCHAR,
    language VARCHAR,
    released_at DATE,
    PRIMARY KEY (card_snapshot_id, printing_id)
);
