# Experimentmatrix

## Verpflichtende Vergleiche

| Experiment | Änderung | Fixiert |
|---|---|---|
| E-B0 | Random | Dataset, Pool, Masken |
| E-B1 | Global/Commander Popularity | Dataset, Pool, Masken |
| E-B3 | Lift/PMI | Dataset, Pool, Masken |
| E-B4 | Card-Card Co-Occurrence | Dataset, Pool, Masken |
| E-MF | Matrix Factorization | Dataset, Featureschnitt |
| E-DS-ID | DeepSets nur ID-Embeddings | Dataset, Budget |
| E-DS-STRUCT | + strukturierte Features | Dataset, Budget |
| E-DS-TEXT | + deterministische Textfeatures | Dataset, Budget |

## Ablationspflicht

DeepSets-Releasebericht trennt mindestens:

- ohne Commandercontext;
- ohne sichtbares Deck;
- ohne Popularitätskorrektur;
- ohne strukturierte Features;
- verschiedene Poolingarten;
- OOV-/New-Card-Segment.

Eine Änderung mehrerer Faktoren gleichzeitig gilt als neues Modell, aber nicht als erklärende Ablation.
