# Release-Gates

Ein Modell-/Optimizer-Release benötigt:

1. vollständiges Manifest und reproduzierbare Config;
2. grüne Schema-, Leakage- und Legalitätstests;
3. Vergleich gegen alle verpflichtenden Baselines;
4. keine signifikante Regression in Coverage/Long Tail ohne akzeptierte ADR;
5. Segmentbericht für Low-Data/Cold Commander;
6. Source-/Terms-Status aller Trainingsinputs;
7. dokumentierte bekannte Grenzen;
8. unabhängigen Optimizer-Validator;
9. unverändertes Testset seit Benchmark-Freeze;
10. signiertes oder gehashtes Release-Manifest.

Ein Notebook-Screenshot oder einzelner Recall-Wert ist kein Releasebeleg.
