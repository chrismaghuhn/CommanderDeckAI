# TopDeck.gg adapter

Status und Zugriff werden ausschließlich durch Source Review und `configs/sources/topdeck.yaml` bestimmt. Der aktuelle Status `PROPOSED` blockiert jede lokale Synchronisierung vor dem ersten Request.

Der Adapter implementiert den dokumentierten Tournaments-v2-Request als begrenzten POST über die gemeinsame HTTP-/Raw-Snapshot-Infrastruktur. Der API-Key wird ausschließlich aus `TOPDECK_API_KEY` (bzw. dem konfigurierten Environment-Namen) gelesen und nur als `Authorization`-Header verwendet. Er gelangt nicht in Request-Provenienz, Manifeste oder Fehlertexte.

Die Parser erzeugen ausschließlich source-shaped DTOs und Staging Records. Event-, Standing-, Deck-, Round-, Table- und Player-Beobachtungen behalten ihre Originalfelder und exakten JSON-Pointer auf das unveränderte Raw-Objekt. Die Entscheidung, ob eine Tabelle als `PodEntry` oder eine Veranstaltung als `EventDeckObservation` gelten darf, bleibt Task 12 vorbehalten.

Implementierter Zuschnitt:

```text
client.py
downloader.py
dto.py
errors.py
json_support.py
parser.py
record_parser.py
round_parser.py
settings.py
staging.py
README.md
```

Live-Netzwerk wird nicht in PR-CI verwendet. Fixtures enthalten keine Credentials und keine realen Teilnehmerdaten. Raw-Snapshots bleiben wegen der aktuellen Approval-/Terms-Lage lokal gated; eine spätere Aktivierung bleibt an `APPROVED_LOCAL` oder `APPROVED_REDISTRIBUTION` sowie die aktuelle Use-Policy gebunden.
