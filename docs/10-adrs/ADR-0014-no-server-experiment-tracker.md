# ADR-0014-no-server-experiment-tracker — Lokale Run-Manifeste vor Tracking-Server

**Status:** Accepted<br>
**Datum:** 2026-08-10


## Entscheidung

Experimenttracking startet als versionierte lokale Artefaktstruktur.

## Begründung

Ein zusätzlicher Server erhöht Betriebskosten, ohne frühe Reproduzierbarkeit zu verbessern.

## Folgen

Manifestformat muss später in MLflow/W&B-artige Adapter importierbar bleiben, aber keine Kernabhängigkeit entsteht.
