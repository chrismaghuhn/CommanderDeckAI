# Mana-Base-Modul

Mana Base wird bewusst als eigenes Subproblem behandelt.

## MVP

- Nutzer kann fixe Länder vorgeben;
- einfacher Landbereich;
- Basic-Land-Verteilung nach Farb-Pips;
- bereits gerankte Utility Lands begrenzt aufnehmen;
- finaler Validator prüft Deckgröße und Color Identity.

## Spätere Version

- farbige Quellen je Zugziel;
- getappte/untapped Quellen;
- Fetch-/Dual-Beziehungen;
- Budget und Sammlung;
- farblose Spezialkosten;
- Commander-spezifische Land-Synergien.

## Trennung

`core_deck` entscheidet Nichtland-Slots und gewünschte Landzahl. `mana_base` erzeugt die konkrete Landauswahl. Beide liefern getrennte Diagnosen und Score-Komponenten.
