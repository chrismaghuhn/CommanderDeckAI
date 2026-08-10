# Commander Deck AI

Nicht-LLM-basierter, datengetriebener Commander-Deckbuilder für reproduzierbare Kartenempfehlung, legale Deckoptimierung und spätere Forge-Evaluation.

## Status

```text
M0 — Foundation / Repository Scaffold
```

Die erste Implementierungsstufe baut noch kein neuronales Modell. Sie etabliert installierbare Projektstruktur, versionierte Verträge, Architekturtests und reproduzierbare lokale Builds.

## Zielarchitektur

```text
Commander + Teildeck + Constraints
                │
                ▼
       legaler Kandidatenpool
                │
                ▼
 nicht-generativer Karten-Ranker
                │
                ▼
 deterministischer CP-SAT-Optimizer
                │
                ▼
 legales, nachvollziehbares 100-Karten-Deck
                │
                ▼
 optional: Turnier- und Forge-Evidenz
```

## Lokaler Start

Voraussetzungen:

- Python 3.12;
- `uv` 0.12.3;
- Git.

```bash
uv lock
uv sync --group dev
uv run cda doctor
uv run pytest
```

Die CI verwendet anschließend ausschließlich den eingecheckten `uv.lock`.

## Wichtige Dokumente

- [`START_HERE.md`](START_HERE.md) — erste Implementierungsreihenfolge;
- [`AGENTS.md`](AGENTS.md) — verbindliche Regeln für Coding-Agents;
- [`PROJECT_TREE.md`](PROJECT_TREE.md) — Zielstruktur;
- [`docs/02-architecture/system-context.md`](docs/02-architecture/system-context.md) — Systemgrenze;
- [`docs/03-data/source-approval-gate.md`](docs/03-data/source-approval-gate.md) — Datenfreigabe;
- [`docs/04-ml/problem-formulation.md`](docs/04-ml/problem-formulation.md) — Ranking-Aufgabe;
- [`docs/05-optimizer/overview.md`](docs/05-optimizer/overview.md) — Deckoptimierung;
- [`docs/09-roadmap/roadmap.md`](docs/09-roadmap/roadmap.md) — Milestones.

## Grundregeln

- kein LLM und keine externe Embedding-API;
- keine nicht genehmigten Scraper;
- immutable Daten-, Regeln-, Feature- und Modell-Snapshots;
- Casual und cEDH werden getrennt bewertet;
- ML rankt Karten, ein deterministischer Optimizer baut das Deck;
- Forge bleibt ein optionaler, versioniert gekoppelter Evaluator;
- kleine, verantwortungsbezogene Module statt Sammeldateien.

## Aktueller Umfang

Der Repository-Scaffold enthält nur `cda doctor` und Architektur-/Vertragsprüfungen. Datenadapter, Ranker, Optimizer und Forge-Brücke werden milestoneweise gemäß `planning/backlog.csv` implementiert.
