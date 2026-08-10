# Gate für Set Transformer

Ein Set Transformer wird nicht gebaut, nur weil er moderner klingt.

## Voraussetzungen

- DeepSets ist sauber implementiert und benchmarked;
- Analyse zeigt Fehler, die auf fehlende Karten-Karten-Interaktion im Set hindeuten;
- Co-Occurrence-/Combo-Subgruppen profitieren plausibel von Attention;
- Memory-/Laufzeitbudget ist dokumentiert;
- gleiche Features, Splits und Trainingsbudgets für fairen Vergleich;
- messbare Verbesserung über mindestens zwei Testsegmente.

## Akzeptanz

Nicht nur globales NDCG betrachten. Verbesserung muss bei komplexen Synergien, Combo-Holes oder Cold-Commander-Segmenten auftreten, ohne Coverage und Long-Tail deutlich zu verschlechtern.

Ein Set Transformer ist weiterhin **kein LLM**; er verarbeitet Kartenfeatures und wird ausschließlich auf dem projektspezifischen Dataset trainiert.
