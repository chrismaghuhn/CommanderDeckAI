# Leakage-Kontrollen

## Automatische Prüfungen

- Fingerprint-Überschneidung zwischen Splits = Fehler;
- Revision-Group-Überschneidung = Fehler;
- Near-Duplicate-Cluster-Überschneidung = Fehler;
- Event-ID über cEDH-Splits = Fehler;
- Feature-Snapshot nach Samplezeit = Fehler;
- aktueller Popularitätscount in historischem Test = Fehler;
- Precon-Klon in Train und Precon-Holdout = Fehler.

## Modellbezogen

- Testlabels dürfen nicht in Candidate-Pool-Heuristik eingebaut werden;
- Combo-Daten müssen zeitlich/versioniert sein, wenn historische Evaluation behauptet wird;
- Commander-Name oder Decktitel darf keine Archetyp-Labels leaken;
- Player-ID ist kein produktives Feature.

Jeder Benchmark erzeugt einen maschinenlesbaren Leakage-Report.
