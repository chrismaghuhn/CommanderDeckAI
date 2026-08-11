# Spicerack Review

**Status:** PROPOSED
**Reviewed:** 2026-08-10
**Decklist API:** https://docs.spicerack.gg/api-reference/public-decklist-database
**API introduction:** https://docs.spicerack.gg/api-reference/introduction

## Verified technical properties

- the documented endpoint is `GET https://api.spicerack.gg/api/export-decklists/`;
- documented query parameters are `num_days`, `event_format`,
  `organization_id`, and `decklist_as_text`;
- documented Commander formats include `COMMANDER2`, `PAUPER_COMMANDER`, and
  `DUEL`;
- the endpoint returns a tournament array and supports JSON and NDJSON;
- the documentation shows API-key authentication and describes the API as beta.

These documented properties are technical evidence only. Public visibility,
beta documentation, or a reachable endpoint is not treated as blanket
permission for bulk acquisition, local retention, or redistribution.

## Access and gates

- The adapter remains blocked until the source registry changes from `PROPOSED`
  and the current-use decision allows `SOURCE_SYNC`/`NORMALIZE`.
- The credential configuration stores only the environment-variable name
  `SPICERACK_API_KEY`; no key may appear in YAML, manifests, logs, or config
  snapshots.
- The adapter accepts only the reviewed host and exact export path. It does not
  implement undocumented paths or scraping.
- Local byte, timeout, retry, rate, response-size, and format limits are safety
  bounds, not claims about provider quotas. The endpoint is not page-paginated;
  one request is made for each configured format.

## Rights and retention assessment

- **Official API:** documented public read API; authentication and account
  eligibility still require confirmation before activation.
- **Authentication:** API key required; the repository does not contain a key.
- **Rate limits:** exact provider quota is not established by this review;
  bounded local rate/retry settings are mandatory.
- **Attribution:** source configuration requires attribution, but exact wording,
  placement, and treatment of tournament/decklist/result content require
  confirmation.
- **Local raw storage:** `pending_terms_review`; raw responses and manifests
  remain blocked while the source is `PROPOSED`.
- **Redistribution:** `not_approved`; neither raw responses nor derived records
  may be exported under this review.
- **PII:** tournament standings may contain player names and linked decklist
  URLs. Staging projections remove direct names/contact fields unless an
  approved use explicitly requires them; source locators and missingness remain.
- **Takedown/deletion:** no universal automated guarantee is claimed. A later
  takedown or terms change must block current use and trigger review of affected
  raw and derived artifacts without mutating historical manifests.

## Implemented project use

The adapter preserves source-shaped event, standing, player/decklist projection,
and result staging records with exact raw locators. It does not create canonical
events, decks, participants, or pods. Missing pod information is missing data
and produces a quality finding; pods are never synthesized from standings.

This review is not a legal opinion or redistribution authorization. Before
changing the status to an approved state, record the applicable terms,
retention, attribution, authentication, and redistribution decisions in the
source registry and configuration.
