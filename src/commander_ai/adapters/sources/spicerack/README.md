# Spicerack adapter

The source remains `PROPOSED` in the source registry. Acquisition is therefore
blocked until the reviewed source status and current-use decision allow local
sync. No live source data is committed to the repository.

The adapter implements only the documented Public Decklist Database read
contract:

```text
GET https://api.spicerack.gg/api/export-decklists/
num_days, event_format, organization_id, decklist_as_text
```

The endpoint returns a JSON array or newline-delimited tournament objects. It
does not expose page pagination; one immutable raw object is acquired per
configured event format. The configured byte, timeout, retry, rate, and format
limits remain active.

For JSON arrays, nested standings receive JSON-pointer locators. For NDJSON,
each tournament line is one logical source record, so its nested standings stay
inside that line's source values and the line receives a byte-range locator.

Responses are written byte-for-byte through the shared raw snapshot writer and
are parsed only after a COMPLETE snapshot has been integrity-verified. Source
DTOs and staging rows retain exact locators; canonical event, deck, participant,
and pod records are outside this adapter. Missing pod data remains missing and
is recorded as a quality finding; no pod is synthesized from standings.

The adapter files are intentionally source-specific:

```text
client.py        documented request and credential handling
downloader.py    bounded raw acquisition
dto.py           permissive source DTOs
errors.py        stable adapter error codes
json_support.py  strict JSON decoding and safe scalar handling
parser.py        verified JSON/NDJSON structural parsing
record_parser.py PII-minimized staging projection
settings.py      source-owned contract settings
staging.py       evidence-bound generic staging/audit rows
```

Tests use fixtures and mocked HTTP responses only. Credentials are read from
the configured environment-variable name and are never persisted in manifests,
configuration snapshots, or errors.
