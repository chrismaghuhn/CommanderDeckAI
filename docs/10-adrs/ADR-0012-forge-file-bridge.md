# ADR-0012-forge-file-bridge — Forge v1 über Dateivertrag koppeln

**Status:** Accepted<br>
**Datum:** 2026-08-10


## Entscheidung

Atomare JSON Request/Result-Dateien statt eingebettetem JVM oder RPC.

## Begründung

Lose Kopplung, einfache Wiederaufnahme, reproduzierbare Jobs und unabhängige Entwicklung.

## Folgen

Höhere Latenz ist akzeptabel. Schema-/Versionprüfung ist zwingend.
