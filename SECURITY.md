# Security und verantwortlicher Datenumgang

## Secrets

API-Schlüssel werden ausschließlich über Umgebungsvariablen oder einen lokalen Secret Store geladen. Sie dürfen weder in YAML-Dateien noch in Run-Manifeste oder Test-Fixtures geschrieben werden.

## Fremddaten

Öffentlich abrufbar bedeutet nicht automatisch bulk-scrapebar oder redistributierbar. Jeder Source-Adapter benötigt eine dokumentierte Freigabeentscheidung. Rohdaten unklarer Quellen dürfen nicht in öffentliche Artefakte oder Git-Historie gelangen.

## Personenbezug

Spieler-, Autor- und Accountnamen werden für Deckbuilding-Training standardmäßig entfernt oder pseudonymisiert. Outcome-Modelle dürfen stabile pseudonyme IDs nur verwenden, wenn dies für Leakage-Kontrolle erforderlich und rechtlich zulässig ist.

## Meldungen

Sicherheits- oder Datenrechtsprobleme werden nicht als öffentliches Issue mit Secrets oder personenbezogenen Beispieldaten eröffnet. Das Projekt soll vor Veröffentlichung einen privaten Kontaktweg in dieser Datei ergänzen.
