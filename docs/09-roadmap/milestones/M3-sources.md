# M3 — Freigegebene Commander-/Turnierquellen

## Ziel

Erweiterung um klar freigegebene Source-Adapter und Resultatdaten.

## Reihenfolge

1. Commander Spellbook;
2. TopDeck.gg, falls Key/Attribution/Terms akzeptiert;
3. Spicerack, falls Beta-Zugang und Terms akzeptiert;
4. cEDH DDB nur für freigegebene Repo-Metadaten; verlinkte Deckinhalte separat prüfen.

## Deliverables

- Source-Review je Adapter;
- Raw/Normalized Snapshots;
- Event/Pod/Result-Schema;
- Contract-Fixtures;
- Attribution-Ausgabe;
- PII-Minimierung.

## Exit-Kriterien

- jeder Adapter idempotent und abschaltbar;
- kein C-Source-Scraping;
- unvollständige Snapshots werden erkannt;
- Outcome-Daten referenziell konsistent;
- Redistributionstatus maschinell durchgesetzt.
