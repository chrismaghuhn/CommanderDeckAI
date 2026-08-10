# Domain

Reine, frameworkunabhängige Typen und Invarianten.

## Darf enthalten

Cards, Decks, Command Zone, Ruleset-Referenzen, Constraints, Provenienz-IDs und stabile Domainfehler.

Strukturelle Kartenzonen lehnen doppelte Card-Identity-Zeilen innerhalb einer Zone ab; Mengen werden nicht
still zusammengeführt, damit die Fingerprint-Eingabe eindeutig bleibt.

`PodEntry` ist eine interne normalisierte Zeile fuer Pod-Runde, Sitz, Ergebnis, Teilnehmer und Provenienz.
Sie ist nicht das `pod.v1`-Envelope aus `schemas/pod.v1.schema.json` und traegt deshalb keinen
`schema_version`-Marker. Das bestehende Multiplayer-Envelope bleibt unverÃ¤ndert.

## Darf nicht enthalten

HTTP, Dateisystem, DuckDB, PyTorch, OR-Tools, CLI, Source-Payloads oder globale Konfiguration.
