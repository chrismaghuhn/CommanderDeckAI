# ADR-0002-no-llm — Kein LLM als Deckbuilding-Kern

**Status:** Accepted<br>
**Datum:** 2026-08-10


## Entscheidung

Ranking, Set-Modelle und kombinatorische Optimierung ersetzen Sprachgeneration.

## Begründung

Decks sind Sets unter harten Regeln. Reproduzierbarkeit, Kandidatenkontrolle und Benchmarks sind wichtiger als freie Textgeneration.

## Folgen

Keine pretrained Language Models oder externe Embeddings. Deterministische Textfeatures bleiben erlaubt.
