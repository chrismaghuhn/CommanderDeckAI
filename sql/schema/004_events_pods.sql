CREATE TABLE IF NOT EXISTS events (
    event_id VARCHAR PRIMARY KEY,
    source_id VARCHAR NOT NULL,
    source_event_id VARCHAR NOT NULL,
    format VARCHAR NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    status VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS pods (
    pod_id VARCHAR PRIMARY KEY,
    event_id VARCHAR NOT NULL,
    round_label VARCHAR NOT NULL,
    occurred_at TIMESTAMP,
    status VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS pod_entries (
    pod_id VARCHAR NOT NULL,
    seat INTEGER NOT NULL,
    deck_id VARCHAR NOT NULL,
    player_pseudonym VARCHAR,
    result VARCHAR NOT NULL,
    placement INTEGER,
    points DOUBLE,
    PRIMARY KEY (pod_id, seat)
);
