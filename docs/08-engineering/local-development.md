# Lokale Entwicklung

## Unterstützte Baseline

Python 3.12, Git und ein C/C++-freier Standardpfad für Kernentwicklung. PyTorch und OR-Tools werden als optionale Extras aktiviert.

## Empfohlene Befehle

```bash
uv sync --group dev
uv run cda doctor
uv run ruff check .
uv run mypy src
uv run pytest
```

ML- und Optimizer-Abhängigkeiten werden nur für die betreffenden Milestones installiert:

```bash
uv sync --group dev --extra ml --extra optimizer
```

Fallback ohne `uv` 0.12.3:

```bash
python -m venv .venv
# .venv aktivieren
python -m pip install --upgrade pip
python -m pip install -e ".[ml,optimizer]" --group dev
```

## Keine globalen Voraussetzungen

Datenbankserver, Docker, Java und Forge sind für M0–M5 nicht erforderlich. Forge wird erst für Bridge-/Simulationstests benötigt.

## Fixtures

Das Repository enthält nur kleine synthetische oder ausdrücklich redistributierbare Fixtures. Vollständige Snapshots werden lokal über CLI erzeugt.
