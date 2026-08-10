# ADR-0001-modular-monorepo — Modulares Monorepo statt Microservices

**Status:** Accepted<br>
**Datum:** 2026-08-10


## Entscheidung

Ein Python-Repository mit klaren Packages und Ports. Keine separaten Services in der initialen Architektur.

## Begründung

Batch-/CLI-Workflows, lokaler Betrieb und kleines Team profitieren von einfacher Installation und atomaren Refactorings. Ports erhalten spätere Deployment-Optionen.

## Folgen

Architekturtests müssen Abhängigkeitsgrenzen schützen. Ein Service darf später nur Adapter sein.
