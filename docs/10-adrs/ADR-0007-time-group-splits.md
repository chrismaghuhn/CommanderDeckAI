# ADR-0007-time-group-splits — Zeitbasierte, gruppengebundene Splits

**Status:** Accepted<br>
**Datum:** 2026-08-10


## Entscheidung

Deckrevisionen, Duplikatcluster und Events bleiben ungeteilt; Test ist zeitlich später.

## Begründung

Random Splits überschätzen Generalisierung durch fast identische Listen und spätere Informationen.

## Folgen

Weniger, aber glaubwürdigere Testdaten. Leakage-Suite ist Releasegate.
