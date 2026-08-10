# Issue Map

Die detaillierte, importierbare Liste liegt unter `planning/backlog.csv`.

## Epics

- `E0` Foundation und Verträge;
- `E1` Card Catalog/Ruleset;
- `E2` Deck Data/Baselines;
- `E3` Source Adapters;
- `E4` Benchmark;
- `E5` Models;
- `E6` Optimizer;
- `E7` cEDH Outcomes;
- `E8` Forge;
- `E9` Casual Product.

## Issue-Größe

Ein Issue soll einen testbaren vertikalen oder klar abgegrenzten horizontalen Schritt darstellen. „Build the ML system“ ist kein Issue. „Implement deterministic mask generator with manifest and property tests“ ist ein Issue.

## Abhängigkeitsregel

Backlog-Zeilen enthalten `depends_on`. Ein Coding-Agent darf keine abhängigen Issues still mitimplementieren; gemeinsame Refactorings werden als eigene Issue/ADR sichtbar gemacht.
