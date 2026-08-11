# M4 — Completion Benchmark Freeze

## Ziel

Ein stabiler Benchmark, gegen den Modelle fair verglichen werden können und der früh genug eingefroren wird, um Plattform-Perfektionismus vor dem ersten echten ML-Signal zu verhindern.

## Deliverables

- zeitlicher Standardholdout;
- getrennte High-Data-, Low-Data- und Cold-Commander-Segmente;
- New-Card- und Precon-Segmente;
- eingefrorene Masken und Candidate Pools;
- Leakage-Suite;
- Baseline-Report für B0–B5;
- Benchmarkmanifest und Checksums;
- versioniertes Minimum-Viable-Freeze-Profil;
- preregistriertes Learnability-/Pivot-Gate gemäß `docs/06-evaluation/learnability-pivot-gate.md`.

## Minimum-Viable-Freeze-Trigger

Vor dem Exit von M3 wird ein versioniertes Freeze-Profil committed. Es bindet mindestens:

- `min_qualified_decks` als konkrete Ganzzahl;
- `min_unique_command_zones` als konkrete Ganzzahl;
- konkrete Temporal-Cutoff-Daten und den geforderten abgedeckten Zeitraum;
- konkrete minimale Train-/Validation-/Test-Samplecounts;
- konkrete minimale Samplecounts für alle geschützten Segmente;
- numerische High-/Low-Data-Commander-Grenzen und die Definition von Cold Commander;
- Maskenregime und Candidate-Pool-Policy;
- primäre/sekundäre Metriken und Anti-Collapse-Guardrails;
- G0/G1/G2-Margins und geschützte Segmentgrenzen;
- Bootstrap-/Unsicherheitsmethode;
- Experiment- und Diagnosebudgets.

Qualitative Platzhalter wie „genug Decks“, „ausreichende Coverage“ oder „hinreichend großer Holdout“ erfüllen das Freeze-Profil nicht. M3 kann nicht als bereit für den M4-Freeze gelten, solange die numerischen Mindestwerte nicht committed sind.

Die konkreten Zahlen werden nicht in diesem Milestone-Dokument geraten. Sie werden aus den bis dahin gemessenen Daten abgeleitet und vor dem ersten entscheidenden M4-Validation-Lauf preregistriert. Danach dürfen sie für Benchmark v1 nicht anhand der beobachteten Gate-Ergebnisse verändert werden.

G2 wird erst in M5 ausgeführt, seine Vergleichsregel wird aber bereits mit Benchmark v1 preregistriert. Dadurch kann die Schwelle nicht nach Sichtung der Matrix-Factorization-Ergebnisse verschoben werden.

Sobald diese Mindestbedingungen erfüllt sind, wird Benchmark v1 eingefroren. Zusätzliche Quellen, schönere Reports, größere historische Coverage oder weitere Plattform-Infrastruktur dürfen den Freeze dann nicht verschieben.

TopDeck/Spicerack sind insbesondere **keine Voraussetzung** für M4, wenn der Completion-Benchmark seine preregistrierten Mindestbedingungen ohne diese Quellen erfüllt. Später verfügbare Daten gehen in eine neue Benchmarkversion statt Benchmark v1 rückwirkend zu verändern.

Falls eine Mindestbedingung nicht erfüllt ist, gilt nur Arbeit als M4-blockierend, die diese konkrete Lücke adressiert.

## Learnability-Gate

M4 entscheidet nicht nur, welcher Baseline-Score höher ist. Es prüft stufenweise:

1. `G0a`: schlägt Global Popularity Random Legal belastbar?
2. `G0b`: liefert Commander-spezifische Evidenz gegenüber Global Popularity Zusatznutzen?
3. `G1`: liefert der sichtbare Deckkontext gegenüber Commander-only Ranking zusätzlichen Predictive Value?
4. werden preregistrierte High-/Low-Data-/Cold-Commander-, Temporal-, Long-Tail- oder Anti-Collapse-Guardrails verletzt?

`NDCG@25` ist die primäre v1-Uplift-Metrik, aber ein gutes Overall-NDCG darf keine geschützte Segment- oder Anti-Collapse-Grenze überstimmen. Catalog Coverage, Long-Tail Recall und Novelty-/Popularity-Verteilung laufen verpflichtend als Sekundärdiagnostik mit.

Das M4-Ergebnis wird als `GREEN`, `YELLOW` oder `RED` dokumentiert. `YELLOW` erlaubt pro Benchmark-/Gate-Version genau eine begrenzte, vorher committed Diagnosephase. Danach muss der Zustand auf `GREEN` oder `RED` aufgelöst werden; ein zweites YELLOW-Budget derselben Gate-Version ist nicht zulässig.

Die Gate-Entscheidung ist mechanisch. Ein knapp verfehlter preregistrierter Margin bleibt verfehlt; Reviewer dürfen einen Wert nicht nachträglich als „praktisch GREEN“ freigeben. Eine geänderte Schwelle benötigt eine neue Gate-/Benchmarkversion vor dem nächsten entscheidenden Validation-Lauf.

`RED` blockiert das blinde Hochskalieren zu komplexeren Modellen. G2 wird anschließend in M5 gegen dieselbe preregistrierte Benchmarkversion ergänzt.

## Exit-Kriterien

- keine Splitüberschneidung;
- jede Metrik mit Samplecounts und Unsicherheitsangabe;
- Baselines auf identischen Pools;
- Testset nicht für Tuning verwendet;
- Freeze-Profil enthält konkrete numerische Mindestwerte statt qualitativer Platzhalter;
- Freeze-Profil und G0/G1/G2-Margins vor entscheidenden Validation-Ergebnissen committed;
- B0–B5 gegen die eingefrorene Learnability-Leiter ausgewertet;
- High-/Low-Data-/Cold-Commander- und weitere geschützte Segmente gemäß Freeze-Profil berichtet;
- GREEN/YELLOW/RED-Entscheidung mechanisch mit Segment-/Anti-Collapse-Belegen dokumentiert;
- Dokumentation ausreichend für unabhängige Reproduktion.
