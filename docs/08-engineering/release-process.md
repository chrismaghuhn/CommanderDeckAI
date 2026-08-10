# Releaseprozess

## Code Release

- Changelog;
- Schema-/ADR-Review;
- vollständige CI;
- Paketbau;
- Checksums;
- signiertes Tag, sofern Repository-Infrastruktur dies erlaubt.

## Dataset Release

- Datasetmanifest;
- Source-/Terms-Matrix;
- Leakage-/Quality-Report;
- Feld-/Tabellendokumentation;
- Checksums;
- keine nicht freigegebenen Rohdaten.

## Model Release

- Modelmanifest;
- Datasetreferenz;
- Baselinevergleich;
- Segment- und Biasreport;
- bekannte Grenzen;
- Gewichte in sicherem Format;
- Beispielinferenz.

Modelle und Datasets erhalten getrennte Versionen; ein Code Release zwingt keinen Modellrelease.
