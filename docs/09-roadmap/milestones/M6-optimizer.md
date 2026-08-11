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
- getrennte Baselines für `A0` Ranker raw Top-K und `A1` Ranker + greedy legal fill;
- Vergleich von `A1` gegen `B` Ranker + CP-SAT mit hard constraints;
- Ablation von `B` gegen `C` mit kalibrierten Auxiliary Objectives.

`A0` ist nur eine Ranking-Kontrollgruppe und kein akzeptiertes vollständiges Deck. Die Trennung verhindert, dass der Effekt trivialer legaler Konstruktion mit dem zusätzlichen Nutzen von CP-SAT vermischt wird.

## Experimentelles Nach-M6-Gate

Iteratives Contextual Re-Score/Repair ist **kein** Exit-Kriterium für M6 und kein automatisch aktivierter Default. Erst nach einem stabilen one-shot Ranker+CP-SAT-Pfad wird geprüft, ob messbare Kontextdrift, Rollenredundanz oder lokale Auswahlfehler einen Repair-Loop rechtfertigen.

Ein Repair-Experiment muss gegen den one-shot Pfad auf eingefrorenen Benchmarks gewinnen, deterministische Fingerprint-basierte Stop-/Zyklusregeln besitzen und die zusätzliche Laufzeit ausweisen. Completion-Metriken allein reichen nicht als Deckqualitätsnachweis.

Details: `docs/05-optimizer/joint-deck-consistency.md`.
