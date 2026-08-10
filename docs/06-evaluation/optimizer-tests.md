# Optimizer-Testmatrix

## Property Tests

Für zufällig generierte Requests:

- Ergebnisgröße stimmt;
- keine verbotene Karte;
- Color Identity eingehalten;
- Copy Limits eingehalten;
- Must-Include enthalten;
- Must-Exclude nicht enthalten;
- Budget und harte Rollenbereiche eingehalten;
- identischer Input/Seed erzeugt identisches Ergebnis.

## Golden Cases

- Single Commander;
- Partner-/mehrteilige Command Zone;
- Basic-Land-Ausnahme;
- kartenspezifische Copy-Limit-Ausnahme;
- banned-as-companion-Sonderfall;
- widersprüchliche Must-Includes;
- zu kleines Budget;
- Collection-only ohne Lösung;
- mehrere gleichwertige Optima.

## Differential Test

Finaler Validator ist unabhängig vom Solver-Modell. Er rekonstruiert das Deck aus dem Ergebnis und prüft alle Regeln erneut.
