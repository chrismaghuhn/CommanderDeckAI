# No-LLM-Policy

## Verboten im Kernsystem

- vortrainierte Sprachmodelle;
- externe Text-Embedding-APIs;
- Prompting als Kartenwahl;
- autoregressive Decklisten-Completion;
- generierte Begründungen als Entscheidungsevidenz.

## Erlaubt

- ID-Embeddings, die ausschließlich aus Deckdaten gelernt werden;
- strukturierte Kartenmerkmale;
- deterministische Oracle-Text-Regeln;
- TF-IDF oder gehashte N-Gramme als optionale nicht-generative Features;
- DeepSets, Matrix Factorization, GNNs oder Set Transformer;
- deterministische Textvorlagen, die vorhandene Score-Komponenten anzeigen.

Jedes Modellmanifest enthält `uses_pretrained_language_model: false`. Ein späterer Architekturwechsel erfordert eine neue ADR und darf diese Baseline nicht stillschweigend verändern.
