# Logging und Observability

## Strukturierte Events

Jedes Event enthält:

- `run_id`;
- `component`;
- `event_code`;
- `entity_id`/`snapshot_id`, falls relevant;
- Dauer/Counts;
- Status;
- keine Secrets oder vollständigen Deck-/Raw-Payloads standardmäßig.

## Metriken pro Job

- gelesene/geschriebene Datensätze;
- Quarantäne- und Finding-Counts;
- Cache Hits;
- Kandidatenpoolgröße;
- Solverstatus;
- Modellbatch-/Fehlercounts;
- Forge-Abbruchcodes.

## Kein Serverzwang

Initial werden JSONL-Logs und Run-Reports geschrieben. Eine spätere Telemetrieplattform ist Adapter, keine Kernabhängigkeit.
