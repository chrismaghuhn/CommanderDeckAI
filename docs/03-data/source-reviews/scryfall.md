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

## Source-Approval-Gate checklist

1. **Official documentation or permission:** The official Scryfall Bulk Data documentation is the reviewed access documentation. Documented availability is not treated as blanket permission to reproduce every card field or associated intellectual property.
2. **Authentication and rate limits:** The configured bulk metadata path has no API key. Current endpoint guidance, response limits, and any access restrictions must be rechecked before activation; the configured timeout, retry, rate, and download limits apply.
3. **Attribution:** Attribution to Scryfall and applicable upstream sources is required in local reports and derived artifacts where the source contributes data.
4. **Local raw storage:** Bulk metadata responses and the downloaded raw object may be stored locally for the configured `APPROVED_LOCAL` path, together with URL, timestamp, content metadata, and checksum evidence. This does not authorize publication.
5. **Normalized derivations:** Local deterministic derivations may retain the card identifiers, oracle identities, faces, rules, color identity, and other fields necessary for the approved card-catalog use. Card images and unnecessary fields remain outside this scope.
6. **Redistribution:** Raw card data, rules text, and other content are not presumed redistributable. Public export requires a separate current content and terms review.
7. **PII:** No player, deck-account, or contact PII is expected in the selected oracle-card bulk data. Unexpected person-linked fields are minimized, quarantined, or excluded from curated output.
8. **Deletion/takedown:** No universal automated deletion guarantee is claimed. A source notice or takedown request pauses affected processing, records the affected bulk object/field, and triggers removal or quarantine of affected derived outputs after review.
9. **Interval and user agent:** Bulk availability is not a requirement to synchronize daily. Use an explicit schedule, an identifiable user agent, and the configured bounds; do not replace the bulk path with mass individual-card requests.
10. **Necessary fields/recommended use:** The necessary fields are the structured card identity and rules/legality inputs required by the card catalog. Recommended use is local card identity and rule-feature derivation without images, prices, or an unrestricted content mirror.

## PII

Keine erwarteten personenbezogenen Deck-/Spielerdaten.
