# Commander Spellbook Review

**Status:** APPROVED_LOCAL<br>
**Reviewed:** 2026-08-10<br>
**Backend:** https://github.com/SpaceCowMedia/commander-spellbook-backend<br>
**Docs:** https://spacecowmedia.github.io/commander-spellbook-backend/

## Geplanter Scope

Combo-IDs, beteiligte Karten, Preconditions, Resultat-/Feature-Tags und Variantbeziehungen.

## Zugriff und Grenzen

- Verwendet werden nur dokumentierte Read-Verträge oder ein ausdrücklich freigegebener Export; undokumentiertes Scraping bleibt ausgeschlossen.
- Die konfigurierte API-Host-Allowlist, Timeout-, Retry-, Rate-, Seiten- und Downloadgrenze gilt vor jeder späteren Adapterverdrahtung.
- Attribution bleibt erforderlich. Lokale Raw-/Normalised-Speicherung ist konfiguriert; Redistribution von Fremdinhalten bleibt einer separaten Inhaltsprüfung unterworfen.
- Empfohlener Einsatz sind Combo-/Kartenbeziehungen als Feature-Fakten, nicht als automatische Legalitäts- oder Gameplay-Garantie.

## Nicht tun

- Combo-Daten als garantierte Gameplay-Wahrheit behandeln;
- externe Kartendaten duplizieren, wenn Oracle-IDs verknüpft werden können;
- Combo-Frequenz ohne Deck-/Zeitkontext als Stärke interpretieren.

## Source-Approval-Gate checklist

1. **Official documentation or permission:** The reviewed official project repository and developer documentation define the documented read contracts. Documentation of public endpoints is not treated as blanket permission for scraping, bulk copying, or redistribution.
2. **Authentication and rate limits:** The current local config has no stored API credential. Endpoint authentication, rate limits, and any export permission must be rechecked before activation; configured timeout, retry, page, and download limits remain mandatory.
3. **Attribution:** Attribution to Commander Spellbook and applicable upstream content is required in local reports and derived artifacts where the source contributes data.
4. **Local raw storage:** Raw responses from the configured documented read path or expressly approved export may be stored locally for this `APPROVED_LOCAL` scope. Storage remains immutable and local; this review does not authorize publication.
5. **Normalized derivations:** Local derivations may retain combo IDs, card relationships, preconditions, result/feature tags, and variant links needed for the project. They remain provenance-bound and are not treated as independent legality or gameplay facts.
6. **Redistribution:** Redistribution of raw responses or derived combo content is not automatically approved. The backend's documented license and the rights in individual or upstream content are reviewed separately before export.
7. **PII:** Player, account, contact, or contributor fields are not necessary for the intended combo use case. If unexpected person-linked data appears, it is minimized, quarantined, or excluded from curated output.
8. **Deletion/takedown:** No universal automated deletion guarantee is claimed. A takedown or source prohibition pauses affected processing, records the relevant locator, and requires removal or quarantine of affected derived outputs after review.
9. **Interval and user agent:** Use bounded, respectful reads of documented endpoints or approved exports, not undocumented polling or scraping. Requests must use an identifiable project user agent and honor current service guidance and configured limits.
10. **Necessary fields/recommended use:** The necessary fields are documented combo/card IDs, preconditions, result or feature tags, and variant relationships. Recommended use is as auditable combo/card relationship features, not as a gameplay, legality, or power guarantee.

## Lizenz

Backend ist als MIT dokumentiert; konkrete API-/Datenattribution und mögliche Fremdinhalte werden vor Redistribution geprüft. Dies ist keine rechtliche Freigabe.
