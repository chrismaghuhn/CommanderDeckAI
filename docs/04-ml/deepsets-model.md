# DeepSets-Ranker

## Motivation

Ein Deck ist ein Set/Multiset; Kartenreihenfolge hat keine Bedeutung. DeepSets bietet eine einfache permutation-invariante Baseline, bevor komplexere Attention-Modelle gerechtfertigt sind.

## Architektur v1

```text
card features ──> card encoder φ ──┐
                                   ├─ mean/sum pooling ─> deck context
visible cards ─────────────────────┘
command-zone cards ─> shared/separate encoder ─> command context
profile features ───────────────────────────────> profile context
candidate card ─────────────────────────────────> candidate vector

concat(deck, command, profile, candidate,
       candidate*deck, candidate*command)
                    │
                    ▼
                 MLP score
```

## Anforderungen

- Masken für variable Setgröße;
- deterministische Pooling-Semantik;
- gemeinsame Karten-ID-Tabelle zwischen Kontext und Kandidat;
- strukturierter Fallback für neue Karten;
- Score-Ausgabe vor Kalibrierung getrennt speichern;
- keine Positionsembeddings.

## Startkonfiguration

Klein beginnen: wenige Encoder-Layer, moderate Embeddinggröße, keine riesige Parameterzahl. Modellgröße wird erst erhöht, wenn Underfitting auf Train/Validation belegt ist.
