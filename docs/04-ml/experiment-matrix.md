# Experimentmatrix

## Verpflichtende Vergleiche

| Experiment | Änderung | Fixiert |
|---|---|---|
| E-B0 | Random Legal | Dataset, Pool, Masken |
| E-B1 | Global Popularity | Dataset, Pool, Masken |
| E-B2 | Commander Popularity | Dataset, Pool, Masken |
| E-B3 | Lift/PMI | Dataset, Pool, Masken |
| E-B4 | Card-Card Co-Occurrence | Dataset, Pool, Masken |
| E-B5 | Hybrid Linear Ranker | Dataset, Pool, Masken, Validation-Budget |
| E-MF | Matrix Factorization | Dataset, Featureschnitt, Validation-Budget |
| E-DS-ID | DeepSets nur ID-Embeddings | Dataset, Budget |
| E-DS-STRUCT | + strukturierte Features | Dataset, Budget |
| E-DS-TEXT | + deterministische Textfeatures | Dataset, Budget |

B0–B5 werden für das M4-Learnability-Gate getrennt ausgewiesen. Insbesondere dürfen Global Popularity und Commander Popularity nicht zu einer einzigen Kontrollgruppe zusammengezogen werden, weil `G0` genau den zusätzlichen Commander-spezifischen Signalwert prüfen soll.

Matrix Factorization wird in M5 vor DeepSets evaluiert. DeepSets-Experimente werden nur gemäß `docs/06-evaluation/learnability-pivot-gate.md` freigegeben.

## Experimentbudgets

Die maximale Anzahl Validation-Konfigurationen und Seeds wird vor dem ersten Search-Lauf im eingefrorenen Benchmark-/Gate-Profil festgelegt. Zusätzliche Runs nach Sichtung der Resultate benötigen eine neue dokumentierte Hypothese; das Testset bleibt davon unberührt.

## Ablationspflicht

DeepSets-Releasebericht trennt mindestens:

- ohne Commandercontext;
- ohne sichtbares Deck;
- ohne Popularitätskorrektur;
- ohne strukturierte Features;
- verschiedene Poolingarten;
- OOV-/New-Card-Segment.

Eine Änderung mehrerer Faktoren gleichzeitig gilt als neues Modell, aber nicht als erklärende Ablation.
