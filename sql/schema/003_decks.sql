CREATE TABLE IF NOT EXISTS decks (
    deck_id VARCHAR PRIMARY KEY,
    format VARCHAR NOT NULL,
    ruleset_version VARCHAR NOT NULL,
    card_snapshot_id VARCHAR NOT NULL,
    title VARCHAR,
    mode VARCHAR NOT NULL,
    deck_fingerprint VARCHAR NOT NULL,
    revision_group_id VARCHAR,
    near_duplicate_cluster_id VARCHAR,
    legal_status VARCHAR NOT NULL,
    source_id VARCHAR NOT NULL,
    source_deck_id VARCHAR NOT NULL,
    observed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS deck_cards (
    deck_id VARCHAR NOT NULL,
    zone VARCHAR NOT NULL,
    oracle_id UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    printing_id UUID,
    PRIMARY KEY (deck_id, zone, oracle_id)
);

CREATE INDEX IF NOT EXISTS idx_decks_fingerprint ON decks(deck_fingerprint);
CREATE INDEX IF NOT EXISTS idx_deck_cards_oracle ON deck_cards(oracle_id);
