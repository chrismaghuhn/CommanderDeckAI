# ADR-0003-ranker-then-optimizer — Ranker und Optimizer getrennt

**Status:** Accepted<br>
**Datum:** 2026-08-10


## Entscheidung

Das Modell erzeugt Scores; ein deterministischer Optimizer wählt das Deck.

## Begründung

Harte Regeln und Nutzerconstraints sind zuverlässig lösbar und überprüfbar. Generative Modelle würden Legalität und Erklärbarkeit erschweren.

## Folgen

Score-Snapshot ist versionierter Vertrag. Optimizer importiert keine Modellklasse.
