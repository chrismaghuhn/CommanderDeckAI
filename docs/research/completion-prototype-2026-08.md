# Completion Prototype Research Note — 2026-08

## Ergebnis

Der isolierte Wegwerf-Prototyp beantwortet die Forschungsfrage mit **YELLOW**:
Commander-Deck-Completion zeigt messbares statistisches Signal. Die Datenbasis und
die Candidate Coverage sind jedoch zu schwach, um daraus bereits eine belastbare
Produktions- oder Modellarchitektur abzuleiten.

## Datengrundlage und Evaluation

- Quelle: offizielles MTGJSON `AllDeckFiles.zip`.
- 192 nutzbare Commander-Decks und 168 eindeutige Command Zones.
- Zeitlich gruppierter Split: 129 Train / 29 Validation / 34 Test.
- Drei deterministische Maskierungen: late (5 Karten), mid (~20 %), early (~50 %).
- Kandidaten: in den Trainingsdecks beobachtete Oracle-IDs, grob nach Color Identity
  gefiltert; dies ist kein vollständiger Commander-Legalitätsfilter.
- Candidate Coverage im Test: **55,0 %**. Out-of-vocabulary-Ziele wurden als
  verfehlte Ziele gewertet.

## Kernergebnisse

- B1 Global Popularity schlägt B0 Random deutlich; die Completion-Pipeline besitzt
  damit grundsätzlich Signal.
- H1 Commander-Signal ist in diesem Lauf nicht estimierbar: Alle Test-Command-Zones
  waren im Training ungesehen, deshalb fielen B2/B3 korrekt auf B1 zurück.
- Reines Visible-Deck-Context-B4 war schwach.
- Der zusätzliche Commander-plus-Context-Vergleich lag bei **+15,4 % NDCG@25**
  gegenüber B2.
- Der validierungsgetunte B5-Hybrid lag bei **+19,0 % NDCG@25** gegenüber B2
  (B2: 0,245; B5: 0,292).
- Die Empfehlungen konzentrieren sich bei B1/B2/B3 stark auf häufige Staples;
  B4 zeigt mehr Long-Tail-Abdeckung, ist aber als reiner Context-Ranker zu schwach.

## Konsequenz

Der Prototyp wird nicht in CommanderDeckAI übernommen. Kein B6, kein DeepSets,
kein CP-SAT- oder Produktions-ML-Ausbau wird aus diesem Ergebnis abgeleitet.
Der nächste sinnvolle Schritt ist später ein breiterer, eingefrorener M4-artiger
Completion-Benchmark mit besserer Candidate Coverage, warmen Commandern und
stärkerer Duplicate-/Revision-Kontrolle.

Die vollständigen Ergebnisartefakte liegen neben dieser Notiz als
`completion-prototype-2026-08-summary.md`,
`completion-prototype-2026-08-metrics.json` und
`completion-prototype-2026-08-examples.md`.
