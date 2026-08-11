# M6 — Deterministischer Deckoptimizer

## Ziel

Aus Rankings vollständige, legale und constraint-konforme Decks erzeugen.

## Deliverables

- Candidate-Pool-Reduktion;
- CP-SAT Core-Deck-Solver;
- Mana-Base MVP;
- Casual-/cEDH-Profile;
- unabhängiger Finalvalidator;
- Infeasibility-Diagnose;
- Score-Breakdown und deterministischer Tie-Break.

## Exit-Kriterien

- 100 % Legalität aller akzeptierten Golden/Property-Ausgaben;
- keine stille Constraint-Relaxation;
- reproduzierbare Solverruns;
- Pool-Sicherheitsprüfung;
- Vergleich gegen greedy Auswahl;
- Ablation des Ranker-only-, Ranker+CP-SAT- und kalibrierten Auxiliary-Objective-Pfads.

## Experimentelles Nach-M6-Gate

Iteratives Contextual Re-Score/Repair ist **kein** Exit-Kriterium für M6 und kein automatisch aktivierter Default. Erst nach einem stabilen one-shot Ranker+CP-SAT-Pfad wird geprüft, ob messbare Kontextdrift, Rollenredundanz oder lokale Auswahlfehler einen Repair-Loop rechtfertigen.

Ein Repair-Experiment muss gegen den one-shot Pfad auf eingefrorenen Benchmarks gewinnen, deterministische Stop-/Zyklusregeln besitzen und die zusätzliche Laufzeit ausweisen. Completion-Metriken allein reichen nicht als Deckqualitätsnachweis.

Details: `docs/05-optimizer/joint-deck-consistency.md`.
