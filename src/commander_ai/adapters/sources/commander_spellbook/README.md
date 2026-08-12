# commander_spellbook adapter

This package implements the approved, read-only Commander Spellbook source
boundary. Full or periodic Data Foundation acquisition uses the documented
bulk JSON product at
`https://json.commanderspellbook.com/variants.json`. Sparse REST reads remain
available for future interactive lookups only.

The source review and registry remain authoritative for access, attribution,
current-use approval, host allowlists, limits, and redistribution status:

- `settings.py` binds the documented REST contracts and bulk product, the two
  allowlisted hosts, and a hard maximum of three REST pages per sparse read.
- `client.py` checks the current `SOURCE_SYNC` decision before either access
  path. It uses the shared HTTP transport, identifiable `CommanderDeckAI/0.1`
  User-Agent, bounded retries/timeouts, `Retry-After`, conservative 30
  requests/minute configuration, response-size limits, and redirect/host
  policy.
- `downloader.py` makes one bulk request for a periodic snapshot. It writes
  the exact response entity bytes through the shared `RawSnapshotStore`,
  finalizes and verifies the raw snapshot, and does not parse or paginate REST
  responses during acquisition.
- `parser.py` and `mapper.py` consume only verifier-issued complete snapshots.
  The bulk envelope is parsed into source DTOs and staging rows only after raw
  finalization; exact raw-object locators remain attached to observations.
- The REST `cards` and `variants` contracts are bounded to pages 1 through 3
  and are not a bulk-export path. A periodic sync cannot silently iterate
  hundreds of REST pages.

HTTP `content-encoding` is retained on each raw-object reference. The raw
entity is hashed and finalized first. Any decompression used for a derived
parser view happens after the immutable raw artifact exists; unsupported or
invalid content remains non-consumable rather than being guessed.

No canonical card, combo, deck, legality, or gameplay entity is created in
this source adapter. Source-shaped DTOs, staging rows, findings, provenance,
and raw locators are the adapter boundary; later pipeline stages own
canonicalization and semantic quality decisions.
