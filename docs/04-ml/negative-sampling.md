# Negative Sampling

Uniforme Negatives sind zu leicht. Das Training verwendet eine dokumentierte Mischung.

## Kategorien

- 25 % uniform aus legalem Pool;
- 25 % gleiche Farbe/ähnlicher Mana Value;
- 20 % gleiche Rolle;
- 15 % hohe globale Popularität;
- 10 % hohe Commander-, aber geringe Deckkontext-Passung;
- 5 % Near-Miss aus ähnlichen Archetypen.

Die Prozentsätze sind Startwerte, keine Wahrheit; Änderungen sind Experimente.

## Regeln

- keine illegalen Karten als normale Negatives;
- keine versteckten Positives aus identischen Deckrevisionen;
- Kandidaten aus demselben Zeit-Snapshot;
- negative Sampling-Seed und Strategie im Sample-/Run-Manifest;
- Validation/Test werden nicht dynamisch neu gesampelt, sondern eingefroren.

## Popularitätskorrektur

Loss- oder Samplinggewichte verhindern, dass das Modell allein durch Staples gewinnt. Coverage und Long-Tail-Recall werden neben Recall@K berichtet.
