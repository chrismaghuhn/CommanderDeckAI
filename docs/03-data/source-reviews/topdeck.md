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

## Task-8-Adaptergrenze

Der implementierte Adapter bleibt wegen `PROPOSED` nicht synchronisierbar. Er verwendet den
dokumentierten `POST /api/v2/tournaments`-Vertrag, sendet bei Formatabfragen pro Request ein
einzelnes `format`-Feld und bindet den exakten Request-Body ueber einen SHA-256-Digest an die
Request-Provenienz. Raw-Response-Bytes werden ueber die gemeinsame Snapshot-Infrastruktur
gespeichert; Parser und Staging erzeugen keine kanonischen Event-, Pod-, Deck- oder
Spielerbeobachtungen. Round-/Table-Daten bleiben source-shaped und werden nicht als 1v1-Matches
interpretiert. Eine spaetere Aktivierung benoetigt weiterhin lokale Source-Approval und eine
aktuelle Use-Policy.

## Source-Approval-Gate checklist

1. **Official API/access:** Reviewed access is the documented TopDeck.gg Tournaments v2 API. The documentation describes the API surface and supported tournament data, but public documentation or reachable endpoints are not treated as blanket permission for bulk acquisition or redistribution. The configured access method, host allowlist, and explicit sync policy remain in force.
2. **Authentication and rate limits:** The configured credential is the environment-variable name `TOPDECK_API_KEY`; no key is stored in this repository. The review records documented API-key and rate-limit requirements, but the current quota, authentication terms, and any access conditions must be rechecked before activation. The configured `rate_limit_per_minute`, retry bound, timeout, page limit, download limit, and `Retry-After` handling are local safety bounds, not a claim about the provider's allowance.
3. **Attribution:** Attribution is indicated as required by the reviewed API documentation. The exact wording, placement, and attribution for upstream or event-provided content remain open and must be recorded before any approved use.
4. **Local raw storage:** The source config keeps `raw_storage: pending_terms_review`. Raw responses, request metadata, and immutable manifests must not be acquired or retained as an approved project path while the source is `PROPOSED`. A later local approval would still need to specify retention, access control, and the exact raw objects allowed to remain local.
5. **Normalized derivations:** If access is later approved, deterministic local derivations may retain only the event, format, date, round/table, decklist, commander, standing, and result fields necessary for the configured use case, with source provenance and missingness preserved. The review does not currently authorize those derivations, and no player/contact field is needed for curated output.
6. **Redistribution:** The config remains `redistribution: not_approved`. Raw responses, decklists, names, standings, and derived result data must not be exported or redistributed under this review. Any future redistribution requires a separate current review of the applicable terms and content rights; this checklist makes no legal guarantee.
7. **PII:** Responses may include player names, stable IDs, email addresses, Discord fields, or other person-linked data depending on event and response. Email/Discord and unnecessary person-linked fields are out of scope for curated datasets; unexpected PII must be minimized, quarantined, or excluded, subject to a documented review.
8. **Deletion/takedown:** No universal automated deletion or takedown guarantee is claimed. A provider, event, participant, or rights notice must pause affected acquisition and downstream processing, record the relevant source locator, and trigger review plus removal or quarantine of affected raw and derived artifacts where required by the applicable decision.
9. **Interval and user agent:** Use bounded, explicit retrievals rather than polling or repeated bulk refreshes. The configured rate/retry limits and `Retry-After` behavior are mandatory local controls. Before activation, the project must confirm the provider's interval and identifiable User-Agent expectations and configure them; this review does not infer compliance from a reachable API.
10. **Necessary fields/recommended use:** Necessary fields are the configured tournament/event identity, format, date, round/table or pod structure when supplied, decklist/commander, standing, and result data needed for an auditable local baseline. Recommended use is local, provenance-bound tournament analysis and offline evaluation; it is not a general content mirror, player directory, or unrestricted redistribution feed.
