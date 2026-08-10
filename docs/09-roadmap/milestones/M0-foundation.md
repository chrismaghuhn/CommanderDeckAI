# M0 — Repository Foundation

## Ziel

Ein installierbares, getestetes Repository mit stabilen Verträgen und Architekturgrenzen, aber noch ohne Live-Daten oder ML.

## Deliverables

- Package-/Test-/Config-Baum;
- `cda doctor`;
- Schema-Validator für Beispiele;
- Run-/Dataset-/Modelmanifest-Typen;
- Architekturimporttests;
- CI;
- Source-Approval-Registry;
- Tiny synthetische Fixtures.

## Exit-Kriterien

- frische Installation aus Lockfile;
- alle Checks grün;
- keine Secrets/Live-Netze;
- v1-Schemas validieren;
- Abhängigkeitsrichtung maschinell geschützt;
- Dateigrößenregel aktiv.
