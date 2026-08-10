# Ziel-Repository-Baum

```text
commander-deck-ai/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── uv.lock
├── configs/
│   ├── sources/
│   ├── datasets/
│   ├── experiments/
│   ├── optimizer/
│   └── forge/
├── schemas/
├── data/                       # nie in Git; nur README/Manifeste
│   ├── raw/
│   ├── normalized/
│   ├── curated/
│   ├── indexes/
│   └── cache/
├── artifacts/                  # Modelle, Reports, Runs; nicht automatisch Git
│   ├── datasets/
│   ├── models/
│   ├── benchmarks/
│   └── forge/
├── sql/
│   ├── normalization/
│   ├── quality/
│   └── datasets/
├── src/commander_ai/
│   ├── domain/
│   │   ├── cards.py
│   │   ├── decks.py
│   │   ├── rulesets.py
│   │   ├── constraints.py
│   │   ├── provenance.py
│   │   └── errors.py
│   ├── application/
│   │   ├── ports/
│   │   └── use_cases/
│   ├── adapters/
│   │   ├── storage/
│   │   ├── http/
│   │   └── sources/
│   │       ├── scryfall/
│   │       ├── mtgjson/
│   │       ├── topdeck/
│   │       ├── spicerack/
│   │       └── commander_spellbook/
│   ├── data_pipeline/
│   │   ├── normalization/
│   │   ├── deduplication/
│   │   ├── quality/
│   │   ├── splitting/
│   │   └── builders/
│   ├── features/
│   │   ├── cards/
│   │   ├── decks/
│   │   ├── roles/
│   │   └── text_rules/
│   ├── models/
│   │   ├── protocol.py
│   │   ├── baselines/
│   │   ├── matrix_factorization/
│   │   └── deepsets/
│   ├── optimization/
│   │   ├── candidate_pool.py
│   │   ├── core_deck/
│   │   ├── mana_base/
│   │   ├── objectives/
│   │   └── validation/
│   ├── evaluation/
│   │   ├── metrics/
│   │   ├── benchmarks/
│   │   ├── reports/
│   │   └── leakage/
│   ├── forge/
│   │   ├── contracts/
│   │   ├── file_bridge.py
│   │   └── result_cache.py
│   ├── config/
│   └── cli/
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   ├── property/
│   ├── golden/
│   └── e2e/
├── notebooks/                  # Exploration only; nie importiert
├── scripts/                    # sehr dünne Wrapper, keine Geschäftslogik
└── docs/
```

## Zuschnittsregel

Packages orientieren sich an **stabilen Verantwortungsgrenzen**, nicht an einzelnen Technologien. PyTorch-Code bleibt beispielsweise unter `models/`, während Datensplitting unabhängig davon unter `data_pipeline/splitting/` liegt.

## Warum kein Microservice-Baum?

Der erste Produktpfad ist Batch-/CLI-basiert und läuft lokal. Separate Services würden Konfiguration, Deployment, Observability und Fehlerflächen vervielfachen, ohne das Kernproblem besser zu lösen. Ports werden trotzdem sauber definiert, damit später ein Service-Adapter ergänzt werden kann.
