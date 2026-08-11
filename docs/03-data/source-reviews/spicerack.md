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

## Source-Approval-Gate checklist

1. **Official API/access:** Reviewed access is the documented Spicerack Public Decklist Database API and its introduction page. The documentation describes a public read contract, but public availability, beta documentation, or a reachable endpoint are not treated as blanket permission for bulk acquisition or redistribution. The configured access method, host allowlist, Commander format filters, and explicit sync policy remain in force.
2. **Authentication and rate limits:** The configured credential is the environment-variable name `SPICERACK_API_KEY`; no key is stored in this repository. The documentation identifies API-key access and a beta API, while the exact quota, authentication terms, and breaking-change policy must be rechecked before activation. The configured `rate_limit_per_minute`, retry bound, timeout, page limit, download limit, and `Retry-After` handling are local safety bounds, not a claim about the provider's allowance.
3. **Attribution:** The source config requires attribution. The exact attribution wording, placement, and treatment of event, decklist, result, and upstream content must be confirmed and recorded before any approved use.
4. **Local raw storage:** The source config keeps `raw_storage: pending_terms_review`. Raw JSON/NDJSON responses, request metadata, and immutable manifests must not be acquired or retained as an approved project path while the source is `PROPOSED`. A later local approval would still need to specify retention, access control, and the exact raw objects allowed to remain local.
5. **Normalized derivations:** If access is later approved, deterministic local staging/derivation may retain only event, format, date, decklist/commander, standings, results, and supplied round/pod fields needed for the configured use case, with source provenance and missingness preserved. Pod structure must not be synthesized when Spicerack does not supply it, and the review does not currently authorize these derivations.
6. **Redistribution:** The config remains `redistribution: not_approved`. Raw responses, decklists, player-linked records, standings, results, and derived artifacts must not be exported or redistributed under this review. Any future redistribution requires a separate current review of the applicable terms and content rights; this checklist makes no legal guarantee.
7. **PII:** Event and tournament payloads may contain player names, IDs, account references, or other person-linked fields; the reviewed documentation is not treated as proof that such fields are absent. Contact data and unnecessary identifiers are out of scope for curated datasets. Unexpected PII must be minimized, quarantined, or excluded, subject to a documented review.
8. **Deletion/takedown:** No universal automated deletion or takedown guarantee is claimed. A source, event, participant, or rights notice must pause affected acquisition and downstream processing, record the relevant source locator, and trigger review plus removal or quarantine of affected raw and derived artifacts where required by the applicable decision. Beta breaking changes also require revalidation rather than silent interpretation.
9. **Interval and user agent:** Use bounded, explicit retrievals rather than polling or repeated bulk refreshes. The configured rate/retry limits and `Retry-After` behavior are mandatory local controls. Before activation, the project must confirm the provider's interval and identifiable User-Agent expectations and configure them; this review does not infer compliance from a reachable API.
10. **Necessary fields/recommended use:** Necessary fields are the configured Commander format, event identity/date, decklist/commander, standings/results, and round/pod structure only when explicitly supplied. Recommended use is local, provenance-bound tournament/decklist analysis and offline evaluation with missing pod data preserved; it is not a general content mirror, gameplay guarantee, or unrestricted redistribution feed.
