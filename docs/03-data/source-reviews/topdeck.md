# TopDeck.gg Review

**Status:** PROPOSED<br>
**Reviewed:** 2026-08-10<br>
**Dokumentation:** https://topdeck.gg/docs/tournaments-v2

## Verifizierte API-Eigenschaften

- dokumentierte Magic-Formate umfassen EDH, Casual EDH, Pauper EDH und Duel Commander;
- Decklisten/strukturierte Deckobjekte können abhängig vom Eventstatus verfügbar sein;
- Runden enthalten Tische/Pods, Spieler und Winner/Status;
- die API verlangt Attribution und hat Rate Limits;
- Responses können Namen, IDs, E-Mail-/Discord-Felder enthalten.

## Zugriff und Grenzen

- Der Adapter bleibt bis zu einer ausdrücklichen Review-/Terms-Freigabe blockiert (`PROPOSED`), auch wenn die API dokumentiert ist.
- Der konfigurierte Credential-Name ist `TOPDECK_API_KEY`; ein Schlüsselwert darf weder in YAML noch in Config-Snapshots stehen.
- Host-Allowlist, Timeout, begrenzte Retries, Rate-Limit/`Retry-After`, Seiten- und Downloadgrenzen sind vor einer späteren Verdrahtung erforderlich.
- Attribution, lokale Raw-/Normalised-Speicherung, Aufbewahrung und Redistribution werden vor Aktivierung konkret bestätigt. Dies ist keine rechtliche Freigabe.

## Projektbegrenzung

Nur notwendige Tournament-, Deck-, Pod- und Resultatfelder abrufen. E-Mail/Discord niemals in Curated Datasets übernehmen. Spielername standardmäßig entfernen; stabile pseudonyme ID nur für Leakage/Bias-Audit, sofern zulässig.

## Offene Freigaben

Lokale Raw-Speicherung, Aufbewahrung, Redistribution abgeleiteter Deck-/Resultatdaten und konkrete Attribution müssen vor Aktivierung dokumentiert werden.
