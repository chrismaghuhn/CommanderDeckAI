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

Runtime-Konfiguration besitzt nur globale Daten-/Artefaktwurzeln und sichere Defaults. Source-Konfiguration besitzt Endpoints, Host-Allowlist, Credential-Env-Namen, Timeout, begrenzte Retries/Raten, Seiten-/Downloadlimits und Source-Filter. Dataset-Konfiguration besitzt task-spezifische Filter, Inklusion/Exklusion, Split-Policy/-Version und Near-Duplicate-Algorithmus/-Version/-Schwelle. RulesetSnapshots bleiben separate Inputs. Operation-Konfiguration referenziert diese Bereiche nur; sie enthält keine Experiment- oder Optimizer-Overrides.

Historische Source-Approval-Metadaten und current-use/takedown-Entscheidungen werden separat versioniert. Aufgelöste Config-Snapshots enthalten keine Secretwerte; nur Env-Namen sind persistierbar. Unbekannte Felder sind Validierungsfehler.
