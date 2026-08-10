# Tests

```text
unit/        reine Funktionen und Domain
contract/    Schemas, Source-/Forge-Verträge
integration/ DuckDB/Parquet und lokale Adapterstubs
property/    Legalität, Deduplikation, Optimizer
 golden/     bewusste, kleine Snapshot-Fixtures
e2e/         Tiny vertikaler Slice
```

Tests dürfen keine privaten API-Schlüssel oder nicht redistributierbaren Daten benötigen.
