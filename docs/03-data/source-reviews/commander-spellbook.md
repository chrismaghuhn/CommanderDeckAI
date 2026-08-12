# Commander Spellbook Review

**Status:** `APPROVED_LOCAL`<br>
**Reviewed:** 2026-08-12<br>
**Backend repository:** <https://github.com/SpaceCowMedia/commander-spellbook-backend><br>
**Developer documentation:** <https://spacecowmedia.github.io/commander-spellbook-backend/><br>
**Review path:** `docs/03-data/source-reviews/commander-spellbook.md`

## Scope and recommended use

The project uses Commander Spellbook for source-shaped combo, card, and
variant observations. Combo knowledge is feature data and is not a legality
authority, gameplay guarantee, or substitute for canonical card facts.

Periodic/full Data Foundation ingestion and sparse interactive lookup are
separate access modes:

| Mode | Access | Project policy |
| --- | --- | --- |
| Periodic/full ingestion | documented bulk JSON | one bulk request, then immutable raw snapshot and downstream normalization |
| Sparse interactive lookup | documented REST `cards`/`variants` reads | bounded pages 1-3 only; never a periodic bulk exporter |

The documented bulk product used by the adapter is:

<https://json.commanderspellbook.com/variants.json>

The project account publicly identified this URL as the downloadable variants
JSON in its announcement:
<https://www.reddit.com/r/magicTCG/comments/1fw2nn4/commander_spellbook_creates_discord_bot/>.
That endpoint evidence is not treated as blanket permission to redistribute
the file or to scrape other endpoints. The backend repository and developer
documentation remain the authoritative references for the REST application
contracts and project code.

The bulk response is expected to be a JSON object containing non-empty
`timestamp` and `version` strings and a `variants` array. The downloaded
response entity bytes, including any content encoding, are persisted exactly
through the shared raw snapshot store before parsing. Extracted/decompressed
views are derived artifacts only.

## Upstream usage guidance and local limits

The upstream usage guidance recorded for this review says that unauthenticated
REST calls should be sparse, that the API must not be used for bulk export over
hundreds of result pages, and that the bulk JSON file should be used for bulk
data and refreshed periodically. It also asks clients to identify themselves
with a service User-Agent and describes approximately 80 requests/minute as a
safe API rate.

CommanderDeckAI uses a stricter policy: the configured rate is 30 requests per
minute, retries are bounded, `Retry-After` is honored, and the REST client
rejects pages above 3 before any request. This is a request-pattern control,
not a claim that rate alone makes bulk REST export acceptable.

## Access, governance, and storage

- Local acquisition is allowed only while the current Source-Approval-Gate
  permits `APPROVED_LOCAL` or `APPROVED_REDISTRIBUTION`. Current-use/takedown
  policy is checked again for every operation.
- Public export or publication requires
  `APPROVED_REDISTRIBUTION`; this review grants no such permission.
- No API key, cookie, authorization header, or secret query parameter is
  configured or persisted. The shared HTTP transport applies the explicit
  safe metadata allowlist and redirect host policy.
- The allowlist contains only
  `backend.commanderspellbook.com` and `json.commanderspellbook.com`.
- Raw snapshots are immutable, local, provenance-bound, and retained for
  audit. Normalized/staging records retain the source snapshot, raw object,
  and exact logical locator. Only later quality-policy-approved projections
  are curated.
- Attribution to Commander Spellbook and applicable upstream content is
  required in local reports and derived artifacts where the source contributes
  data.
- Redistribution of raw or derived content remains subject to a separate
  license/content review. The backend's documented MIT license does not by
  itself settle rights in every data field or upstream card content.
- Unexpected player, account, contact, or contributor fields are minimized,
  quarantined, or excluded. Takedown or source prohibition pauses processing
  and requires review of affected derived artifacts.

## Source-Approval-Gate checklist

1. Official repository and developer documentation are recorded above. The
   publicly announced bulk URL is documented as an acquisition location, not a
   redistribution authorization.
2. The configured access is unauthenticated and uses no stored credential.
   Authentication, service limits, and any changed export terms must be
   rechecked before changing the adapter policy.
3. The bulk path is the only periodic/full acquisition path.
4. The REST path is limited to sparse interactive reads and may not be used to
   enumerate the full dataset.
5. Shared timeout, retry, rate, User-Agent, response-size, redirect, raw
   integrity, and current-use gates remain mandatory.
6. Failed parsing, resolution, and semantic quality records remain auditable;
   no malformed source record is silently discarded.

This is a conservative engineering assessment, not legal advice.
