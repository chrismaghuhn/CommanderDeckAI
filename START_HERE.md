# Start hier

## Empfohlener Projektname

```text
commander-deck-ai
```

Das Projekt sollte **ein eigenes Repository** neben Forge/ForgeAI sein. Die Verbindung zu Forge erfolgt erst über einen versionierten Dateivertrag. Dadurch bleiben Datenerfassung, ML und Deckoptimierung unabhängig vom JVM-Regelwerk.

## Repository-Root erzeugen

```bash
python bootstrap_repository.py ../commander-deck-ai
cd ../commander-deck-ai
uv lock
uv sync --group dev
uv run cda doctor
```

Das Bootstrap-Skript akzeptiert nur ein neues oder leeres Zielverzeichnis und überschreibt keine bestehende Arbeit. Alternativ kann der Baum unter `scaffold/` manuell übernommen werden.

## Erste umzusetzende Baseline

Nicht sofort Deep Learning bauen. Der erste nutzbare vertikale Slice ist:

```text
Scryfall/MTGJSON-Snapshot
→ kanonische Karten
→ Commander-Legalitätsfilter
→ manuell importierte oder offizielle Decks
→ Popularitäts-/Co-Occurrence-Ranker
→ Masked-Deck-Completion-Benchmark
```

Erst wenn diese Kette reproduzierbar ist und Leakage-Tests besteht, folgt Matrix Factorization oder DeepSets.

## M0-Arbeitsauftrag

1. Repository aus `scaffold/` anlegen.
2. `blueprints/pyproject.toml` als Ausgangspunkt übernehmen und einen Lockfile erzeugen.
3. CI aus `blueprints/github/ci.yml` aktivieren.
4. JSON-Schemas unverändert als v1-Verträge übernehmen.
5. `cda doctor` als minimale CLI implementieren.
6. Architekturtests ergänzen, die verbotene Imports verhindern.
7. Noch **keine** Live-Datenquelle und kein ML-Modell implementieren.

## Definition von „baubar“

Ein Milestone darf erst beginnen, wenn der vorherige Milestone seine Exit-Kriterien erfüllt. Für M0 bedeutet das:

- frische Installation aus Lockfile funktioniert;
- Lint, Typprüfung und Tests sind grün;
- Paketrichtung ist maschinell geprüft;
- Schema-Beispiele validieren;
- kein Code benötigt API-Schlüssel;
- keine Datei im Kernpaket überschreitet die Größenregeln ohne dokumentierte Ausnahme.

## Standardentscheidungen

| Bereich | Entscheidung |
|---|---|
| Sprache | Python 3.12 als Kompatibilitätsbaseline |
| Paket-/Lock-Tool | `uv` 0.12.3; Standard-`venv` bleibt Fallback |
| Daten | Parquet + DuckDB, immutable Snapshots |
| Konfiguration | kleine YAML-Dateien, beim Laden typisiert validiert |
| CLI | Typer oder gleichwertige dünne CLI-Schicht |
| Baselines | Popularität, Lift/PMI, Card-Card-Co-Occurrence |
| erstes neuronales Modell | DeepSets-Ranker |
| Optimierung | OR-Tools CP-SAT |
| Forge-Kopplung | versionierte JSON-Dateien, kein Netzwerk in v1 |
| Experimenttracking | lokale Artefaktmanifeste, kein Serverzwang |
| Deployment | lokal/Batch; kein Microservice in den ersten Milestones |

## Nicht überspringen

Die Datenquellen-Freigabe unter `docs/03-data/source-approval-gate.md` ist ein technisches Gate. Ein Adapter gilt nicht als fertig, wenn er technisch Daten laden kann, aber Lizenz, Attribution, Speicherung oder Redistribution ungeklärt sind.
