# Source-Approval-Gate

Vor Implementierung oder Aktivierung eines Adapters muss eine Source-Review-Datei folgende Punkte beantworten:

1. Offizielle Dokumentation oder ausdrückliche Erlaubnis vorhanden?
2. Authentifizierung und Rate Limits?
3. Attribution erforderlich?
4. Dürfen Raw Responses lokal gespeichert werden?
5. Dürfen normalisierte Ableitungen gespeichert werden?
6. Dürfen Roh- oder abgeleitete Daten weiterverteilt werden?
7. Enthält die Quelle personenbezogene Daten?
8. Lösch-/Takedown-Prozess?
9. Abrufintervall und User-Agent-Anforderung?
10. Welche Felder sind tatsächlich für den Use Case notwendig?

## Freigabestatus

```text
PROPOSED → REVIEWED → APPROVED_LOCAL → APPROVED_REDISTRIBUTION
                     ↘ REJECTED / PAUSED
```

`APPROVED_LOCAL` erlaubt nicht automatisch das Veröffentlichen eines Dataset-Snapshots.

## Technische Durchsetzung

- jeder Source-Config enthält `approval_status`;
- CLI verweigert Sync bei nicht freigegebenem Status;
- Raw Manifest speichert Terms-/Policy-Version und Abrufdatum;
- öffentliche Exportjobs filtern Quellen ohne Redistribution-Freigabe.

Die technische Allowlist ist exakt: lokaler Sync erlaubt nur `APPROVED_LOCAL` und `APPROVED_REDISTRIBUTION`; öffentliche Exporte erlauben nur `APPROVED_REDISTRIBUTION`. `PROPOSED`, `REVIEWED`, `REJECTED` und `PAUSED` sind blockiert.

Historische Snapshot-Freigabe und aktuelle Nutzung sind getrennte Registry-Datensätze. Normalize, Validate, Report, Dataset-Build und Public Export benötigen eine aktuelle Entscheidung mit Grund und effektivem Zeitpunkt. `REJECTED`, `PAUSED`, Takedown und ausdrückliche Prohibition blockieren die spätere Verarbeitung auch bei historischer Freigabe.

Dies ist keine Rechtsberatung und keine Garantie für Terms, Lizenzen oder Weitergaberechte.

Dies ist keine Rechtsberatung, sondern ein verpflichtendes technisches Risikogate.

## Registry configuration boundary

The individual files under `configs/sources/` are source-owned settings and
assessment material. Acquisition uses a separately reviewed, strict
`SourceRegistry` document that binds settings and historical approval metadata;
current-use/takedown decisions are an independent field when required by the
operation. A source settings file alone is not evidence that the source may be
synchronized.

The gates are allowlists, not blocklists:

- local `source sync`: only `APPROVED_LOCAL` and
  `APPROVED_REDISTRIBUTION`;
- public export/publish: only `APPROVED_REDISTRIBUTION` plus an allowed current-use
  decision;
- `PROPOSED`, `REVIEWED`, `REJECTED`, and `PAUSED`: blocked.

The historical approval stored in a raw snapshot records what was true at
acquisition time. Current-use/takedown policy is evaluated again for normalize,
validate, report, dataset build, and export. Secrets are represented only by
environment-variable names and are never copied into manifests or run snapshots.
