# M8 — Forge Evaluation Bridge

## Ziel

Reproduzierbare Simulationsevidenz über einen kleinen Dateivertrag.

## Deliverables

- Request/Result v1;
- atomare Queue;
- Version-/Hashprüfung;
- Sitzrotation/Seed-Scheduler;
- Resultcache;
- Abort-/Mismatch-Reporting;
- Vergleichsreport für Kandidatendecks.

## Exit-Kriterien

- idempotente Wiederaufnahme;
- keine Netzwerkabhängigkeit;
- abgebrochene Games nicht als Loss;
- Forge-/Agentversion vollständig gebunden;
- Simulation nur als relative Evidenz dargestellt.
