# commander_spellbook adapter

This package implements the approved, read-only Commander Spellbook Task 7
boundary. It requests only the documented `cards` and `variants` REST
contracts, stores response bytes through the shared raw snapshot writer, and
parses verified snapshots into permissive source-shaped DTOs and Task 5
staging/audit rows.

The source review and registry remain authoritative for access, attribution,
current-use approval, host allowlists, limits, and redistribution status:

- `settings.py` validates the source-owned contract and rejects unknown filters.
- `client.py` builds bounded GET requests through shared HTTP redirect, host,
  retry, rate, timeout, and response-size policy.
- `downloader.py` persists immutable response bytes and never follows an
  upstream pagination URL directly.
- `api_models.py` retains documented fields and unknown forward-compatible
  fields without creating canonical entities.
- `parser.py` consumes only verifier-issued `COMPLETE` snapshots and emits
  exact JSON-pointer/record-index locators, including lossless malformed
  payload envelopes.
- `mapper.py` maps parse observations to the shared staging and audit layers;
  semantic quarantine and later domain relationships are out of scope.
