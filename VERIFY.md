# Paket verifizieren

## Designpaket ohne Repository-Bootstrap

Die JSON-Dateien selbst lassen sich nur mit der Standardbibliothek parsen:

```bash
python -m json.tool schemas/deck.v1.schema.json > /dev/null
python -m json.tool examples/deck.v1.json > /dev/null
```

Für die vollständige Vertragsprüfung wird `jsonschema` benötigt. In einer Umgebung mit den Dev-Abhängigkeiten:

```bash
python scaffold/scripts/validate_examples.py
python scaffold/scripts/validate_fixture_consistency.py
python scaffold/scripts/check_file_sizes.py
python scaffold/scripts/check_architecture.py
```

Das Designpaket enthält keine API-Schlüssel und keine heruntergeladenen Fremddaten.

## Repository automatisch erzeugen

```bash
python bootstrap_repository.py ../commander-deck-ai
cd ../commander-deck-ai
uv lock
uv sync --group dev
uv run cda doctor
uv run python scripts/validate_examples.py
uv run python scripts/validate_fixture_consistency.py
uv run python scripts/check_file_sizes.py
uv run python scripts/check_architecture.py
uv run pytest
```

Das Zielverzeichnis muss neu oder leer sein. Das Bootstrap-Skript überschreibt keine vorhandenen Dateien.

## Manuelle Übernahme

1. Inhalt von `scaffold/` in einen leeren Repository Root kopieren;
2. Root-Dokumente, `configs/`, `schemas/`, `examples/`, `planning/` und `docs/` hinzufügen;
3. `blueprints/pyproject.toml` als `pyproject.toml` übernehmen;
4. `blueprints/sql/` als `sql/` übernehmen;
5. CI- und Dotfile-Blueprints übernehmen;
6. Lockfile erzeugen;
7. Tests und CI ausführen.
