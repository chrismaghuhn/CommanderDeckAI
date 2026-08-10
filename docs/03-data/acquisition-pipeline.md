# Acquisition Pipeline

## Source-Adapter-Aufgaben

1. Anfrageparameter deterministisch erzeugen;
2. Rate Limits und Retry-After respektieren;
3. Antworten unverändert als Raw Objects speichern, soweit erlaubt;
4. Checksums und Response-Metadaten schreiben;
5. Paginierung vollständig und idempotent durchführen;
6. keine Normalisierung im HTTP-Client verstecken;
7. Abrufabbruch als unvollständigen Snapshot markieren.

## Snapshot-ID

```text
{source_id}-{utc_date}-{adapter_version}-{content_prefix}
```

## Idempotenz

Ein abgeschlossener Snapshot wird nie überschrieben. Ein erneuter Abruf erzeugt einen neuen Snapshot, selbst wenn der Inhalt identisch ist; Deduplikation erfolgt über Content Hash und kann Speicher über Hardlinks/Object Store sparen.

## Adapterstruktur

```text
source_name/
├── client.py       # HTTP/Dateizugriff
├── api_models.py   # nur Source-Payloads
├── mapper.py       # Source → Canonical
├── settings.py
├── errors.py
└── README.md
```
