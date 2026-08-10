# Kandidatenpool-Reduktion

Alle legalen Commander-Karten gleichzeitig zu optimieren ist unnötig teuer. Der Pool wird nachvollziehbar reduziert.

## Immer enthalten

- Must-Includes;
- bereits vorhandene Karten;
- notwendige Combo-Closure-Karten;
- genügend Kandidaten je harter Rolle;
- Basic Lands und Mana-Base-Grundmenge;
- Karten, die vom Nutzer explizit erlaubt/gewünscht wurden.

## Scorebasierte Aufnahme

- globale Top-N;
- Top-N pro Rolle;
- Top-N pro Mana-Value-Bucket;
- Top-N für Thema/Combo;
- Diversity-Sample aus Long Tail.

## Sicherheitsprüfung

Vor Solverstart wird bewiesen, dass der reduzierte Pool jede harte Mindestanforderung grundsätzlich erfüllen kann. Sonst wird der Pool erweitert oder ein klarer Vorfehler ausgegeben.

Poolregeln und Hash werden im Optimization Request gespeichert.
