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

## Portable Pfade in versionierten Vertraegen

Neue persistierte Pfade verwenden die strikte portable Pfadsemantik: ein nichtleerer,
POSIX-artiger relativer Pfad aus nichtleeren Segmenten; ausgeschlossen sind absolute
Praefixe, Laufwerks- und UNC-Praefixe, Backslashes, NUL-Zeichen, `.`, `..`,
Tilde-Segmente sowie die Marker `<external-root>` und `<repository-root>`. Die
JSON-Schemas erzwingen diese Regeln mit echten `pattern`/`not`-Constraints; die
`x-*`-Metadaten dokumentieren sie nur zusaetzlich.

`source-snapshot-manifest.v2` und `dataset-manifest.v2` sind die strikten
versionierten Pfadvertraege. `normalized-snapshot-manifest.v1` bleibt als Task-1-
Vertrag unveraendert; sein strikter Nachfolger ist
[`normalized-snapshot-manifest.v2`](../../schemas/normalized-snapshot-manifest.v2.schema.json)
mit dem passenden [Beispiel](../../examples/normalized-snapshot-manifest.v2.json).
Die bestehenden v1-Schemas bleiben lesbare Legacy-Vertraege und werden nicht still
nachtraeglich verschaerft. Neue Produzenten schreiben keine Legacy-Markerpfade.

Die v1-zu-v2-Migration ist eine Validierungsgrenze, keine automatische Pfadkorrektur:
Alle Pfadfelder werden gegen den strikten Vertrag geprueft. Nur wenn jedes Feld gueltig
ist, darf die Migration die `schema_version` auf v2 setzen und die uebrigen Werte
unveraendert uebernehmen. Bei einem Legacy-Pfad bleibt der Datensatz v1-kompatibel und
benoetigt eine explizit dokumentierte Quellzuordnung oder Quarantaene; generische
Metadaten duerfen die semantische Aenderung nicht verstecken.

## Kein „latest“ in Artefakten

Manifeste dürfen intern nie nur `latest` referenzieren. CLI-Komfortaliases werden vor Run-Start in konkrete IDs aufgelöst.
