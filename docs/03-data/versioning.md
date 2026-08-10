# Daten- und Schemaversionierung

## Semantische Ebenen

- `schema_version`: Form und Semantik eines Vertrags;
- `ruleset_version`: Commander-Regeln/Banlist;
- `card_snapshot_id`: Kartenkatalog zu einem Zeitpunkt;
- `source_snapshot_id`: konkreter Source-Abruf;
- `dataset_id`: Filter, Splits und Inputs;
- `model_version`: Modellarchitektur + Gewichte;
- `optimizer_profile_version`: Ziele und Constraints.

## Breaking Changes

Feldumbenennung, Semantikänderung oder neue Pflichtinvariante erzeugt eine neue Major-Schemaversion. Migrationen liegen als eigenständige, getestete Transformationsschritte vor.

## Kein „latest“ in Artefakten

Manifeste dürfen intern nie nur `latest` referenzieren. CLI-Komfortaliases werden vor Run-Start in konkrete IDs aufgelöst.
