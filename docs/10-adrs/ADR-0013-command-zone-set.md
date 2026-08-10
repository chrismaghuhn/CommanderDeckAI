# ADR-0013-command-zone-set — Command Zone als Set statt einzelnes Commander-Feld

**Status:** Accepted<br>
**Datum:** 2026-08-10


## Entscheidung

Domain und Schemas modellieren ein Command-Zone-Set mit variabler Größe.

## Begründung

Partner- und andere regelbasierte Kombinationen dürfen nicht als Sonderhack um ein einzelnes Feld wachsen.

## Folgen

Ruleset validiert Kombinationen; Embeddings poolen mehrere Command-Zone-Karten.
