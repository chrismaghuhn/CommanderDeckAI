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
