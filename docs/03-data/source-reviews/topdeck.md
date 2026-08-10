# TopDeck.gg Review

**Status:** PROPOSED<br>
**Dokumentation:** https://topdeck.gg/docs/tournaments-v2

## Verifizierte API-Eigenschaften

- dokumentierte Magic-Formate umfassen EDH, Casual EDH, Pauper EDH und Duel Commander;
- Decklisten/strukturierte Deckobjekte können abhängig vom Eventstatus verfügbar sein;
- Runden enthalten Tische/Pods, Spieler und Winner/Status;
- die API verlangt Attribution und hat Rate Limits;
- Responses können Namen, IDs, E-Mail-/Discord-Felder enthalten.

## Projektbegrenzung

Nur notwendige Tournament-, Deck-, Pod- und Resultatfelder abrufen. E-Mail/Discord niemals in Curated Datasets übernehmen. Spielername standardmäßig entfernen; stabile pseudonyme ID nur für Leakage/Bias-Audit, sofern zulässig.

## Offene Freigaben

Lokale Raw-Speicherung, Aufbewahrung, Redistribution abgeleiteter Deck-/Resultatdaten und konkrete Attribution müssen vor Aktivierung dokumentiert werden.
