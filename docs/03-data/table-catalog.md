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
