# commander_spellbook adapter

This package implements the approved, read-only Commander Spellbook Task 7
boundary. It requests only the documented `cards` and `variants` REST
contracts, stores response bytes through the shared raw snapshot writer, and
parses verified snapshots into permissive source-shaped DTOs and Task 5
staging/audit rows.

The source review and registry remain authoritative for access, attribution,
current-use approval, host allowlists, limits, and redistribution status:

- `settings.py` binds the reviewed `https://backend.commanderspellbook.com/api/`
  path, `cards`/`variants` products, host, and source limits; unknown or
  conflicting settings are rejected.
- `client.py` receives the same `SourcePolicy` as the downloader and checks the
  current `SOURCE_SYNC` decision and registry-bound settings before metadata or
  body requests. It builds bounded GET requests through shared HTTP redirect,
  host, retry, rate, timeout, and response-size policy.
- `downloader.py` persists immutable response bytes and never follows an
  upstream pagination URL directly. Every page must have the documented
  envelope and source-owned pagination links; malformed, truncated, or
  unreadable pages fail the snapshot instead of ending pagination.
- HTTP `content-encoding` is retained on each raw-object reference. The raw
  entity is hashed and finalized first; bounded `gzip`/`deflate` decoding then
  supplies the derived JSON view used for pagination, parsing, and locator
  validation. Unsupported codings remain non-consumable rather than being
  guessed or silently treated as identity.
- `api_models.py` retains documented fields and unknown forward-compatible
  fields without creating canonical entities, while documented numeric,
  boolean, and text scalars are validated strictly.
- `parser.py` consumes only verifier-issued `COMPLETE` snapshots and emits
  exact JSON-pointer locators, including lossless malformed payload
  envelopes. Byte/payload compatibility calls are checked against the same
  verified object and its product/request identity.
- `mapper.py` accepts only records bound to the same verified snapshot and
  maps parse observations to the shared staging and audit layers; raw source
  values remain in both layers. Semantic quarantine and later domain
  relationships are out of scope.
