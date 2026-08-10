# Arbeitsregeln für Coding-Agents

Diese Datei ist bindend für automatisierte Implementierung in diesem Repository.

## Vor jeder Änderung

1. aktiven Milestone lesen;
2. relevante ADRs lesen;
3. betroffene Schemas und Package-README lesen;
4. `git status`, `git diff --stat`, `git diff`, `git diff --check` prüfen;
5. keine Arbeit aus späteren Milestones vorziehen.

## Harte Grenzen

- Kein LLM, keine Prompt-Pipeline, kein externer Text-Embedding-Dienst.
- Keine Live-Netzwerkzugriffe aus `domain`, `application`, `models`, `optimization` oder `evaluation`.
- Kein Source-Adapter ohne Source-Review und explizite Konfiguration.
- Kein undokumentiertes Scraping.
- Kein „god module“, kein allgemeines `utils.py`, `helpers.py` oder `common.py`.
- Keine versteckte I/O in Datenklassen, Modellen oder Scorern.
- Keine Notebook-Logik, die Produktionscode ersetzt.
- Keine Änderung eines v1-Schemas ohne neue Schemaversion und Migration.
- Keine Zufallsoperation ohne expliziten Seed im Run-Manifest.
- Keine Forge-Abhängigkeit im Python-Kern; nur der Bridge-Adapter kennt das Austauschformat.

## Dateigröße und Zuschnitt

- 250 Zeilen sind eine weiche Warnschwelle.
- 400 Zeilen sind eine harte Grenze für handgeschriebenen Produktionscode.
- Ausnahmen: generierte Dateien, statische Tabellen und JSON-Schemas.
- Eine Datei besitzt genau einen klar formulierbaren Änderungsgrund.
- Nicht künstlich jede Funktion in eine eigene Datei zerlegen; Package-Kohäsion ist wichtiger als minimale Zeilenzahl.

## Abhängigkeitsrichtung

```text
domain
  ↑
application
  ↑
adapters / data_pipeline / models / optimization / evaluation / forge
  ↑
cli
```

`domain` importiert nichts aus höheren Schichten. `application` kennt nur Ports/Protokolle, nicht DuckDB, HTTP, PyTorch oder OR-Tools.

## Qualität vor Featuremenge

Jeder PR enthält:

- fokussierte Tests;
- aktualisierte Dokumentation bei Vertragsänderungen;
- deterministische Fixtures;
- keine API-Schlüssel oder Fremddaten;
- `diff --check` ohne Fehler;
- Erklärung neuer Daten-/Modellartefakte im Manifest.

## Verbotene Abkürzungen

- Testdaten als Produktionsdaten behandeln;
- exakte Deckduplikate über Splits verteilen;
- Ergebnisdaten ohne Event-/Zeitgruppierung splitten;
- Legalität aus Trainingsdaten ableiten statt aus dem versionierten Ruleset;
- Optimizer-Ausgaben ohne finalen Validator akzeptieren;
- Modellscore als „Power Level“ ausgeben;
- Casual-Qualität allein mit Winrate definieren.
