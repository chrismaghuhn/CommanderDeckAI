# Score Snapshots

Ein Rank Response ist eine nutzerorientierte Top-K-Ansicht. Der Optimizer benötigt dagegen einen vollständigen, unveränderlichen Score-Snapshot für seinen reduzierten Kandidatenpool.

## Inhalt

- Score-Snapshot-ID;
- Modell, Dataset, Feature-Spec und Ruleset;
- Hash des Rank Requests und des Candidate Pools;
- alle an den Optimizer zugelassenen Kandidaten;
- Roh-, normalisierte und gewichtete Score-Komponenten;
- Unsicherheit und Warning Codes;
- Erstellungszeit und SHA256.

## Warum eigener Vertrag?

- Optimizer-Runs bleiben reproduzierbar, auch wenn das Modell später geändert wird;
- Top-K-Ausgabe kann klein bleiben;
- Scorekalibrierung und Poolreduktion sind auditierbar;
- ein Solver-Bug lässt sich ohne Modellneuberechnung reproduzieren.

Rank Response referenziert `score_snapshot_id`; Optimization Request ebenfalls.
