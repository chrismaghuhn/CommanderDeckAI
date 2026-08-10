# Spicerack Review

**Status:** PROPOSED<br>
**Decklist-API:** https://docs.spicerack.gg/api-reference/public-decklist-database<br>
**API-Einführung:** https://docs.spicerack.gg/api-reference/introduction

## Verifizierte Eigenschaften

- Public Decklist Database beschreibt Tournament-Decklisten und Resultate;
- `COMMANDER2`, `PAUPER_COMMANDER` und `DUEL` sind dokumentierte Formate;
- API-Schlüssel erforderlich;
- Dokumentation kennzeichnet die API als Beta und warnt vor Breaking Changes.

## Architekturfolge

Payloadmodelle bleiben strikt adapterlokal. Contract-Fixtures und klare Versionfehler sind Pflicht. Der Adapter wird unabhängig von TopDeck implementiert, auch wenn beide in dasselbe kanonische Event-/Pod-Schema mappen.
