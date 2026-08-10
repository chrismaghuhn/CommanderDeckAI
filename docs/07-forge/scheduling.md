# Forge-Jobplanung

## Initial

Eine lokale Queue aus Request-Dateien. Ein expliziter Worker nimmt Jobs atomar in Besitz. Kein Message Broker.

## Priorisierung

- Contract-/Smoke-Jobs;
- kleine Paarvergleiche;
- Candidate-Sweeps;
- große Meta-/Pod-Evaluationen.

## Wiederaufnahme

Resultate sind pro Game/Seed idempotent. Ein unterbrochener Batch erzeugt nur fehlende Subjobs neu.

## Kapazitätskontrolle

Decksuche darf nicht unbeschränkt Forge-Jobs erzeugen. Jeder Optimization Run besitzt ein Evaluationsbudget und eine Candidate-Selection-Policy. Simulation folgt erst, wenn Offline-Scores und Legalität bestanden sind.
