# M4 — Completion Benchmark Freeze

## Ziel

Ein stabiler Benchmark, gegen den Modelle fair verglichen werden können und der früh genug eingefroren wird, um Plattform-Perfektionismus vor dem ersten echten ML-Signal zu verhindern.

## Deliverables

- zeitlicher Standardholdout;
- Cold-Commander-, New-Card- und Precon-Segmente;
- eingefrorene Masken und Candidate Pools;
- Leakage-Suite;
- Baseline-Report für B0–B5;
- Benchmarkmanifest und Checksums;
- versioniertes Minimum-Viable-Freeze-Profil;
- preregistriertes Learnability-/Pivot-Gate gemäß `docs/06-evaluation/learnability-pivot-gate.md`.

## Minimum-Viable-Freeze-Trigger

Vor dem Exit von M3 wird ein versioniertes Freeze-Profil committed. Es bindet mindestens:

- minimale Anzahl qualitätsgeprüfter Decks;
- minimale Commander-/Command-Zone-Abdeckung;
- Temporal-Cutoffs und minimale Split-/Segment-Samplecounts;
- Maskenregime und Candidate-Pool-Policy;
- primäre/sekundäre Metriken;
- G0/G1-Margins und geschützte Segmentgrenzen;
- Bootstrap-/Unsicherheitsmethode;
- Experimentbudgets.

Sobald diese Mindestbedingungen erfüllt sind, wird Benchmark v1 eingefroren. Zusätzliche Quellen, schönere Reports, größere historische Coverage oder weitere Plattform-Infrastruktur dürfen den Freeze dann nicht verschieben.

TopDeck/Spicerack sind insbesondere **keine Voraussetzung** für M4, wenn der Completion-Benchmark seine preregistrierten Mindestbedingungen ohne diese Quellen erfüllt. Später verfügbare Daten gehen in eine neue Benchmarkversion statt Benchmark v1 rückwirkend zu verändern.

Falls eine Mindestbedingung nicht erfüllt ist, gilt nur Arbeit als M4-blockierend, die diese konkrete Lücke adressiert.

## Learnability-Gate

M4 entscheidet nicht nur, welcher Baseline-Score höher ist. Es prüft stufenweise:

1. `G0`: schlagen einfache Popularitäts-/Commander-Signale Random Legal belastbar?
2. `G1`: liefert der sichtbare Deckkontext gegenüber Commander-only Ranking zusätzlichen Predictive Value?
3. gibt es unakzeptierte Temporal-/Cold-/Long-Tail-Regressionsmuster?

Das Ergebnis wird als `GREEN`, `YELLOW` oder `RED` dokumentiert. `YELLOW` erlaubt nur ein begrenztes Diagnosebudget; `RED` blockiert das blinde Hochskalieren zu komplexeren Modellen.

## Exit-Kriterien

- keine Splitüberschneidung;
- jede Metrik mit Samplecounts und Unsicherheitsangabe;
- Baselines auf identischen Pools;
- Testset nicht für Tuning verwendet;
- Freeze-Profil und Gate-Margins vor entscheidenden Validation-Ergebnissen committed;
- B0–B5 gegen die eingefrorene Learnability-Leiter ausgewertet;
- GREEN/YELLOW/RED-Entscheidung mit Segmentbelegen dokumentiert;
- Dokumentation ausreichend für unabhängige Reproduktion.
