# ADR-0006-immutable-snapshots — Immutable Source-, Dataset- und Run-Snapshots

**Status:** Accepted<br>
**Datum:** 2026-08-10


## Entscheidung

Abgeschlossene Snapshots werden nie überschrieben und über Hashes referenziert.

## Begründung

Quellen, Regeln und Meta ändern sich; reproduzierbare Evaluation benötigt konkrete Zustände.

## Folgen

`latest` wird vor Run-Start aufgelöst. Speicherbereinigung respektiert Manifeste.
