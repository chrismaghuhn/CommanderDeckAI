# Forge Request/Response

## File Bridge v1

```text
exchange/
├── requests/{request_id}.json
├── claimed/{request_id}.json
├── results/{request_id}.json
├── failed/{request_id}.json
└── archive/
```

Schreibvorgänge erfolgen atomar über temporäre Datei + Rename.

## Request-Pflichtfelder

- Schema-/Request-ID;
- Deckfingerprints und vollständige Decks;
- Command-Zone-Zonen;
- Ruleset-/Card-Snapshot;
- Forge-/Agent-Kompatibilitätsanforderung;
- Seeds und Sitzrotationen;
- maximale Turn-/Wallclock-Grenzen;
- gewünschte Telemetriestufe.

## Result-Pflichtfelder

- Status;
- tatsächlich verwendete Versionen;
- Ergebnis je Game;
- Sitz, Seed und Winner/Draw/Abort;
- Fehlercodes;
- Laufzeit-/Turn-Metadaten;
- Request- und Result-Hash.

Die konkreten v1-Beispiele stehen unter `schemas/` und `examples/`.
