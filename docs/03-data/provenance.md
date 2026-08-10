# Provenienz

Jede normalisierte Zeile muss auf mindestens ein Source-Objekt zurückführbar sein.

## Erforderliche Felder

- `source_id`;
- `source_snapshot_id`;
- `source_object_id`;
- `retrieved_at`;
- `raw_sha256`;
- `adapter_version`;
- `mapper_version`;
- `approval_status`;
- `terms_reference`;
- `attribution_required`;
- `redistribution_status`.

## Transformationslinie

Datasetmanifeste listen alle Input-Snapshots und SQL-/Codeversionen. Modellmanifeste referenzieren genau ein Datasetmanifest. Optimizer-Ergebnisse referenzieren einen Score-Snapshot und ein Ruleset.

Ohne vollständige Linie gilt ein Artefakt als nicht releasefähig.
