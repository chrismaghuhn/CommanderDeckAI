# Runtime-Topologie

## Initial

Ein lokaler Prozess führt explizite CLI-Kommandos aus. Daten und Artefakte liegen im Dateisystem. DuckDB dient als Query Engine über Parquet.

## Warum Batch-first?

- Source-Sync, Dataset-Build und Training sind natürliche Batch-Jobs;
- reproduzierbare Dateien sind leichter zu debuggen als versteckter Servicezustand;
- ein Solo-/Kleinteam benötigt keine permanente Infrastruktur;
- Forge kann über einen robusten Request/Result-Ordner gekoppelt werden.

## Spätere Erweiterung

Eine HTTP-API darf nur als weiterer Adapter über dieselben Application Use Cases gebaut werden. Kein Domain- oder Modellcode darf von FastAPI oder einem anderen Webframework abhängen.
