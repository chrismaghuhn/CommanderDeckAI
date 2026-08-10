# Performance- und Komplexitätsbudget

## Datenpipeline

- Tabellen streamen oder per DuckDB verarbeiten;
- keine vollständige Deck-Card-Matrix als dichtes Array;
- Parquet-Spalten nur bei Bedarf lesen;
- Source-Payloads seitenweise verarbeiten;
- Near-Duplicate-Suche über Blocking/MinHash statt all-pairs.

## Ranking

- Kandidaten in Batches;
- Kartenfeatures vorab materialisieren;
- Command-/Deckcontext einmal pro Request berechnen;
- Top-K-Heuristiken dürfen nicht die Benchmark-Candidate-Pools verändern.

## Optimizer

- Defaultpool begrenzen und rollenweise absichern;
- nur signifikante Pairwise-Kanten;
- Mana Base getrennt;
- Solverlimits und Status immer berichten.

## Speicherschutz

Jeder Job besitzt konfigurierbare Zeilen-, Byte- und Kandidatengrenzen. Überschreitungen werden als klare Fehler behandelt, nicht durch Prozessabsturz.
