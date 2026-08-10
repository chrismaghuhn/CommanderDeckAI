# ADR-0009-cp-sat — OR-Tools CP-SAT für Deckauswahl

**Status:** Accepted<br>
**Datum:** 2026-08-10


## Entscheidung

Harte diskrete Constraints und gewichtete Ziele werden als CP-SAT formuliert.

## Begründung

Deckauswahl ist binär/integer und enthält viele logische Regeln. Solverstatus und Infeasibility sind explizit.

## Folgen

Scores werden integerquantisiert. Candidate-Pool-Reduktion und unabhängiger Validator sind Pflicht.
