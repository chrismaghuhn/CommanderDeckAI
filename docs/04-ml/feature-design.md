# Feature-Design

## Karten-ID-Embedding

Lernt Co-Occurrence-Wissen. Unbekannte Karten benötigen zusätzlich strukturierte Features.

## Strukturierte Features

- Color Identity und Farben;
- Mana Value und Kosten-Symbole;
- Supertypes, Types und Subtypes;
- Keywords;
- Power/Toughness/Loyalty, soweit relevant;
- Legalitäts- und Release-Snapshot;
- mehrwertige Rollen-Tags;
- Combo-Mitgliedschaft und Combo-Grad;
- Popularität ausschließlich aus Trainingsdaten.

## Oracle-Text ohne LLM

MVP:

- versionierte reguläre Regeln/Parser für häufige Rollen;
- Keyword-/Phrase-Multihots;
- optional gehashte Wort-/Zeichen-N-Gramme.

Kein vortrainiertes Sprachmodell und keine externe Embedding-API.

## Deck-/Profilfeatures

- sichtbare Rollenverteilung;
- Mana-Kurve;
- Farb-Pip-Verteilung;
- gewünschte Rolle-/Landbereiche;
- Budget-/Collection-Flags;
- Casual/cEDH-Modus;
- zeitlicher Snapshot.

Alle Features besitzen eine eigene Version und werden im Modellmanifest referenziert.
