# Konfigurationsstrategie

## Regeln

- kleine YAML-Dateien pro Source, Dataset, Experiment und Optimizerprofil;
- beim Start in typisierte Pydantic-Settings laden;
- unbekannte Felder sind Fehler;
- relative Pfade werden gegen Repository Root aufgelöst;
- Secrets kommen nie aus eingecheckten YAML-Dateien;
- jeder Run speichert die vollständig aufgelöste Config als Snapshot.

## Keine magische Vererbung

Konfigurationen dürfen höchstens eine explizite `extends`-Referenz besitzen. Mehrstufige, implizite Merge-Kaskaden werden vermieden.

## Trennung

Source-Konfiguration bestimmt Zugriff und Rate Limit. Dataset-Konfiguration bestimmt Filter/Splits. Experiment-Konfiguration bestimmt Modell/Training. Optimizer-Konfiguration bestimmt Constraints/Ziele. Diese Bereiche dürfen sich nicht gegenseitig überschreiben.
