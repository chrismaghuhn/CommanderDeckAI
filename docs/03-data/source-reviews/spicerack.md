# Spicerack Review

**Status:** PROPOSED<br>
**Reviewed:** 2026-08-10<br>
**Decklist-API:** https://docs.spicerack.gg/api-reference/public-decklist-database<br>
**API-Einführung:** https://docs.spicerack.gg/api-reference/introduction

## Verifizierte Eigenschaften

- Public Decklist Database beschreibt Tournament-Decklisten und Resultate;
- `COMMANDER2`, `PAUPER_COMMANDER` und `DUEL` sind dokumentierte Formate;
- API-Schlüssel erforderlich;
- Dokumentation kennzeichnet die API als Beta und warnt vor Breaking Changes.

## Zugriff und Grenzen

- Der Adapter bleibt bis zu einer ausdrücklichen Review-/Terms-Freigabe blockiert (`PROPOSED`).
- Der konfigurierte Credential-Name ist `SPICERACK_API_KEY`; ein Schlüsselwert darf weder in YAML noch in Config-Snapshots stehen.
- Host-Allowlist, Timeout, begrenzte Retries, Rate-/`Retry-After`, Seiten- und Downloadgrenzen sowie die Commander-Formatfilter sind explizit zu konfigurieren.
- Attribution, lokale Speicherung, Aufbewahrung und Redistribution werden vor Aktivierung konkret bestätigt. Dies ist keine rechtliche Freigabe.

## Architekturfolge

Payloadmodelle bleiben strikt adapterlokal. Contract-Fixtures und klare Versionfehler sind Pflicht. Der Adapter wird unabhängig von TopDeck implementiert, auch wenn beide in dasselbe kanonische Event-/Pod-Schema mappen.
