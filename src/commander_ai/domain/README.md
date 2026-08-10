# Domain

Reine, frameworkunabhängige Typen und Invarianten.

## Darf enthalten

Cards, Decks, Command Zone, Ruleset-Referenzen, Constraints, Provenienz-IDs und stabile Domainfehler.

Strukturelle Kartenzonen lehnen doppelte Card-Identity-Zeilen innerhalb einer Zone ab; Mengen werden nicht
still zusammengeführt, damit die Fingerprint-Eingabe eindeutig bleibt.

## Darf nicht enthalten

HTTP, Dateisystem, DuckDB, PyTorch, OR-Tools, CLI, Source-Payloads oder globale Konfiguration.
