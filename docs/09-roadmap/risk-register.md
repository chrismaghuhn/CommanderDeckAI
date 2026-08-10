# Risikoregister

| Risiko | Wirkung | Mitigation/Gate |
|---|---|---|
| unklare Source-Rechte | Daten/Modelle nicht veröffentlichbar | Approval Gate, lokale/Redistribution getrennt |
| Decklisten-Bias | Modell kopiert Popularität | Lift-Baseline, Gewichtung, Coverage/Long Tail |
| Split-Leakage | unrealistische Metriken | Fingerprints, Revision-/Near-Duplicate-Gruppen |
| Regeln ändern sich | falsche Legalität | Ruleset-Snapshots, keine `latest`-Artefakte |
| Casual-Ziel falsch | cEDH-artige Decks für Casual | getrennte Profile, Human Pairwise Tests |
| Turnierbias | Outcome ≠ Deckstärke | separater Reranker, Calibration/Uncertainty |
| Optimizer unwartbar | schwer testbare Fehler | Core/Mana/Validator getrennt, kleine Objective-Module |
| Solver infeasible | keine Ausgabe | Conflict-Diagnose, sichere Poolerweiterung |
| Forge-Agent schwach | falsche Performanceaussage | relative Evidenz, Versionbindung, Baselines |
| neue Karten/OOV | schlechte Generalisierung | strukturierte Features, New-Card-Test |
| PII/Spielernamen | Datenschutzproblem | Minimierung/Pseudonymisierung |
| Modell-/Datastaleness | veraltete Empfehlungen | zeitliche Snapshots, Release-/Freshness-Bericht |
| Scope Creep | Projekt bleibt unfertig | Milestone-Gates, keine UI/RL vor Kernqualität |
