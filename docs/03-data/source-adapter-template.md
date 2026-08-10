# Source-Adapter-Template

## README-Pflichtfelder

- Zweck und zugelassene Datenfelder;
- offizielle Dokumentationslinks;
- Approval-Status;
- Authentifizierung;
- Rate Limits und Backoff;
- Attribution;
- lokale Speicherung und Redistribution;
- Paginierung;
- bekannte Datenlücken;
- Golden Fixtures;
- Abschalt-/Takedown-Verfahren.

## Öffentliche Funktionen

```python
class SourceAdapter(Protocol):
    source_id: str

    def acquire(self, request: SnapshotRequest) -> RawSnapshotManifest: ...
    def normalize(self, snapshot: RawSnapshotManifest) -> NormalizedSnapshotManifest: ...
```

`acquire` und `normalize` bleiben getrennt, damit Rohverträge und Mapper unabhängig getestet und versioniert werden können.
