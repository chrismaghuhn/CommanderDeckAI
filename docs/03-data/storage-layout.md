# Speicherlayout

```text
data/
├── raw/{source}/{snapshot_id}/
│   ├── objects/
│   └── manifest.json
├── normalized/{source}/{snapshot_id}/
│   ├── *.parquet
│   └── manifest.json
├── curated/{dataset_id}/
│   ├── train/
│   ├── validation/
│   ├── test/
│   ├── reports/
│   └── manifest.json
├── indexes/
└── cache/
```

## Regeln

- Raw und Curated sind immutable;
- `cache/` ist jederzeit löschbar;
- DuckDB-Dateien sind lokale Query-Caches, nicht die alleinige Wahrheit;
- Parquet-Dateien werden nach Source/Snapshot oder Split partitioniert;
- keine einzelne JSON-Datei mit Millionen Decks;
- große Listen werden gestreamt und nicht vollständig als Python-Objekte geladen.

## Kanonische Artefaktbytes und Digest-Domänen

Persistierte JSON-Manifeste verwenden genau dieselbe kanonische Serialisierung: UTF-8,
lexikografisch nach Unicode-Codepoints sortierte Objekt-Schlüssel, `ensure_ascii=false`,
die Trenner `,` und `:`, keine zusätzlichen Leerzeichen und keinen abschließenden
Zeilenumbruch. Array-/Listenreihenfolgen bleiben erhalten. Nicht-JSON-Werte werden
abgewiesen; sie werden nicht per String-Konvertierung in ein Manifest übernommen.

Die drei SHA-256-Domänen sind getrennt und dürfen nicht gegeneinander ausgetauscht werden:

- `objects[].sha256` ist der Hash der exakten, unveränderten Raw-Objektbytes. Jede Änderung
  an diesen Bytes erzeugt eine andere Eingabe für diese Digest-Domäne.
- `snapshot_content_sha256` ist der Hash der kanonischen Bytes von genau
  `{"objects":[{"bytes":123,"raw_object_id":"object-a","sha256":"..."}]}`.
  Die Einträge werden ausschließlich nach `raw_object_id` in Unicode-Codepoint-Reihenfolge
  sortiert; Request-Metadaten und ein Manifest-Digest gehören nicht in diesen Payload.
- Der detached `manifest.sha256`-Sidecar ist der Hash der kanonischen Manifestbytes nach
  Entfernung ausschließlich des dokumentierten Feldes `manifest_sha256`. Andere Felder,
  insbesondere verschachtelte Hashfelder oder ein `sha256`-Wert, bleiben Bestandteil der
  Eingabe. Der Sidecar ist kein Raw-Objekt- und kein Snapshot-Content-Digest.

`<external-root>` und `<repository-root>` sind ausschließlich nicht reloadbare Marker in
aufgelösten Konfigurations-Snapshots. Sie sind keine gültigen gespeicherten Artefaktpfade.
Alle tatsächlichen Artefaktpfade bleiben nichtleer, POSIX-artig, root-relativ und dürfen
keinen Symlink- oder Traversal-Escape aus dem konfigurierten Root ermöglichen.
