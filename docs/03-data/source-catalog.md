# Datenquellen-Katalog

**Klassifikation:**

- **A — initial geeignet:** dokumentierter Bulk/API-/Open-Source-Zugang; trotzdem Terms beachten.
- **B — geeignet mit Zugang/Attribution:** dokumentierte API, aber Key, Rate Limits oder besondere Pflichten.
- **C — permission-gated:** öffentlich sichtbar, aber kein belastbarer Bulk-/Redistributionspfad.
- **D — Referenz/außer Scope:** nützlich als Benchmark oder Recherche, nicht initialer Trainingsfeed.

| Quelle | Klasse | Geplanter Nutzen | Initialer Adapterstatus |
|---|---:|---|---|
| Scryfall Bulk Data | A | kanonische Karten, Oracle-Text, Typen, Color Identity, Legalities | M1 |
| MTGJSON AllDeckFiles/AllPrintings | A | offizielle Deckprodukte, ergänzende IDs/Metadaten | M1/M2 |
| Commander Spellbook | A | strukturierte Combo- und Kartenbeziehungen | M3 |
| TopDeck.gg Tournaments v2 | B | cEDH/EDH Decks, Events, Standings, Runden/Pods | M3, Key + Attribution |
| Spicerack Public Decklist DB | B | Tournament-Decklisten und Resultate | M3, Beta/API-Key |
| manuelle User-Imports | A | private/eigene Trainings- und Produktdaten | M2 |
| cEDH Decklist Database Repo | B/C | kuratierte Archetypen/Metadaten; verlinkte Deckinhalte separat prüfen | M3 optional |
| EDHREC | C | aggregierte Baseline/Recherche; kein Default-Scraper | später/Permission |
| Archidekt | C | großer Casual-Korpus | nur mit klarer Erlaubnis oder User-Export |
| Moxfield | C | großer Casual/cEDH-Korpus | nur mit klarer Erlaubnis oder User-Export |
| Spellbinder.gg | C | Commander-Event-/Deckdaten | Terms/API klären |
| MTGDecks.net | C | Event-/Decklisten | Terms/API klären |
| EDHcheck | C | Community-Decks | Terms/API klären |
| TableCommander | C | Community-Decks | Terms/API klären |
| Wizards Decklist-Seiten | D | manuelle Ground-Truth-Fixtures | nicht als Bulk-Scraper |
| 17Lands | D | Methodik-/Pretraining-Forschung, nicht Commander | separater Forschungszweig |
| MTGODecklistCache/Kaggle | D | Constructed-Vortraining/Forschung | nicht Commander-Kern |

## Wichtige Regel

Die technische Existenz einer URL oder internen API ist keine Freigabe. Klasse C bleibt deaktiviert, bis der Source-Review eine konkrete erlaubte Zugriffsmethode und Speicher-/Redistributionsregel dokumentiert.
