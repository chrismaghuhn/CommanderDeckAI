# Optimizer-Übersicht

Der Ranker beantwortet „Wie passend ist Karte X?“. Der Optimizer beantwortet „Welche Kombination erfüllt das gesamte Deckproblem?“.

```mermaid
flowchart LR
    R[Rank Scores] --> P[Candidate Pool Reduction]
    C[User Constraints] --> P
    P --> O[Core Deck CP-SAT]
    O --> M[Mana Base Module]
    M --> V[Independent Validator]
    V --> D[Deck + Score Breakdown]
```

## Phasen

1. legalen Pool filtern;
2. Kandidaten pro Rolle/Thema reduzieren, Must-Includes erhalten;
3. Nichtland-Core optimieren;
4. Mana Base ergänzen/optimieren;
5. Gesamtdeck unabhängig validieren;
6. Score-Komponenten und Relaxationen ausgeben.

Die Trennung verhindert einen unwartbaren Ein-Datei-Solver und erlaubt frühe MVPs mit fixer oder einfacher Mana Base.
