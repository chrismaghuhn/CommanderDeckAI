CREATE TABLE IF NOT EXISTS combos (
    combo_id VARCHAR PRIMARY KEY,
    source_id VARCHAR NOT NULL,
    source_combo_id VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    result_tags VARCHAR[] NOT NULL,
    prerequisite_tags VARCHAR[] NOT NULL
);

CREATE TABLE IF NOT EXISTS combo_cards (
    combo_id VARCHAR NOT NULL,
    oracle_id UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    role VARCHAR NOT NULL,
    PRIMARY KEY (combo_id, oracle_id, role)
);
