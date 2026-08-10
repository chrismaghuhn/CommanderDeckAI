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

Dies ist keine Rechtsberatung, sondern ein verpflichtendes technisches Risikogate.
