# Tabellenkatalog

## `cards.parquet`

Eine Zeile pro kanonischer Kartenidentität und Karten-Snapshot.

Schlüssel: `card_snapshot_id`, `oracle_id`.

## `printings.parquet`

Konkrete Ausgaben mit Scryfall-/MTGJSON-IDs, Set, Sprache, Finish und optional Preisreferenz.

## `rulesets.parquet`

Versionierte Format-/Banlist-Snapshots.

## `decks.parquet`

Deckheader: Source, externe ID, Zeit, Command-Zone-Fingerprint, Legalitätsstatus, Tags.

## `deck_cards.parquet`

`deck_id`, `zone`, `oracle_id`, `quantity`, optional `printing_id`.

## `events.parquet`

Eventmetadaten ohne eingebettete Decklisten.

## `pods.parquet`

Event, Runde, Pod-ID, Zeit, Status.

## `pod_entries.parquet`

Pod, Sitz, Deck-ID, Ergebnis, Punkte, Platzierung.

## `combos.parquet` / `combo_cards.parquet`

Normalisierte Combo-Metadaten und Kartenmultiset.

## `quality_findings.parquet`

Stabile Finding-Codes, Severity, Entity-ID und Details.

## `provenance.parquet`

Source-Objekt, Snapshot, Rohhash, Mapperversion, Terms-Review und Transformationslinie.
## Task-5 staging and audit tables

`staging.parquet` preserves source DTO values and exact raw locators without canonical
identity requirements. `audit.parquet` retains namespaced findings, provenance, and
every resolution attempt. `quarantine.parquet` retains failed observations and their
reason codes. None of these tables is a curated output; all are rebuildable from the
verified raw snapshot and the immutable normalized manifest.

## Task-12 event and combo projections

Event-level final standings are stored separately from round/pod `PodEntry` rows.
Pod normalization keeps all seats under one `pod_id`; it never creates synthetic
one-versus-one matches. Participant references are source-, event-, or
snapshot-object-scoped and curated artifacts do not contain raw names or handles.

`canonical_events`, `event_deck_observations`, `canonical_pods`,
`canonical_pod_entries`, `participant_references`, `canonical_combos`,
`canonical_combo_cards`, and `combo_commander_compatibility` are derived DuckDB
projections. The normalized Parquet rows, audit/quarantine rows, exact raw locators,
and their manifests remain authoritative and sufficient to rebuild these tables.
The versioned `event.v1`, `pod.v2`, and
`combo-commander-compatibility.v1` contracts define the newly persisted row
semantics; no event or combo result is inferred from a different source snapshot.
