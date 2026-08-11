# Scryfall Bulk Data Review

**Status:** APPROVED_LOCAL<br>
**Reviewed:** 2026-08-10<br>
**Offizielle Dokumentation:** https://scryfall.com/docs/api/bulk-data

## Geplanter Scope

Nur strukturierte Kartendaten, keine Kartenbilder. Bulk-Download statt massenhafter Einzelrequests.

## Technische Pflichten

- Bulk-Metadaten zuerst abrufen;
- Download-URL, Updated-at, Content-Type, Größe und SHA256 speichern;
- User-Agent/Rate-/Nutzungsbedingungen prüfen;
- Kartentext/IP nicht pauschal als frei redistributierbar behandeln;
- tägliche Verfügbarkeit bedeutet nicht, dass täglich synchronisiert werden muss.

Die Konfiguration verwendet nur den dokumentierten Bulk-Host, einen User-Agent-Env-Namen sowie begrenzte Timeout-, Retry-, Rate-, Seiten- und Downloadwerte. Lokale Speicherung ist konfiguriert; öffentliche Weitergabe bleibt separat zu prüfen.

## PII

Keine erwarteten personenbezogenen Deck-/Spielerdaten.
