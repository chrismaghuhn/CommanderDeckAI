# Contributing

## Pull-Request-Schnitt

Ein PR sollte genau einen dieser Typen haben:

- Vertrags-/Schemaänderung;
- Source-Adapter;
- Dataset-Transformation;
- Modell-/Baseline-Experiment;
- Optimizer-Funktion;
- Benchmark/Testinfrastruktur;
- Dokumentation/ADR.

Source-Adapter und Modelländerung gehören nicht in denselben PR.

## Pflichtprüfungen

```text
format
lint
typecheck
unit tests
contract tests
schema example validation
architecture import checks
diff check
```

Live-APIs werden in normaler PR-CI nicht aufgerufen. Adaptertests verwenden gespeicherte, redigierte Golden Fixtures.

## Commit-Regel

Commits sollen absichtlich und revertierbar sein. Daten-Snapshots, Modellgewichte und große Reports gehören nicht in normale Code-Commits.

## Dokumentationsregel

Eine Änderung an Verhalten, Schema, Source-Policy oder Abhängigkeitsrichtung ist ohne passende Dokumentationsänderung unvollständig.
