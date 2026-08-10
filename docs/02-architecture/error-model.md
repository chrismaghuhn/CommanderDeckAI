# Fehlermodell

## Domänenfehler

- `InvalidDeckError`
- `RulesetMismatchError`
- `ConstraintConflictError`
- `UnknownCardIdentityError`

## Datenfehler

- `SourceContractError`
- `NormalizationError`
- `DataQualityGateError`
- `DatasetManifestError`

## Modell-/Optimizerfehler

- `ModelCompatibilityError`
- `CandidatePoolEmptyError`
- `OptimizationInfeasibleError`
- `ScoreSnapshotMismatchError`

## Regel

Fehler werden am Adapterrand in maschinenlesbare CLI/API-Ausgaben übersetzt. Interne Schichten geben keine freien Fehlermeldungsstrings als einzige Information weiter. Jeder Fehler trägt einen stabilen Code und relevante IDs, aber keine Secrets oder vollständigen Raw Responses.
