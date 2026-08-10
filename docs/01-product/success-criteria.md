# Erfolgskriterien

## Technisch

- 100 % der freigegebenen Optimizer-Ausgaben bestehen den unabhängigen Legalitätsvalidator;
- jeder Run ist über Manifest, Seed, Config, Codeversion und Dataset reproduzierbar;
- Schema- und Source-Änderungen brechen nicht stillschweigend alte Artefakte;
- die Kernschichten sind ohne Netzwerk testbar.

## ML

- jede neue Modellstufe schlägt mindestens die direkt vorherige Baseline auf dem eingefrorenen Testset;
- Verbesserung wird nicht nur in Recall, sondern auch in Coverage, Novelty und Popularitäts-Bias geprüft;
- Cold-Commander- und zeitlicher Holdout werden separat berichtet.

## Produkt

- Nutzerconstraints werden ohne versteckte Relaxation eingehalten;
- Infeasibility wird erklärt statt mit illegalem Deck kaschiert;
- Casual- und cEDH-Ausgaben sind klar getrennt gekennzeichnet;
- Empfehlungen sind komponentenweise nachvollziehbar.
