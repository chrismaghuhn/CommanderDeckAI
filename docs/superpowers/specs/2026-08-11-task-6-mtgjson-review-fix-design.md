# Task 6 MTGJSON Review Fix Design

## Goal

Close the first Task 6 MTGJSON review findings in the existing `data-foundation`
checkout while keeping the adapter at the raw archive -> parse/structural finding
-> Task-5 staging boundary.

## Scope

The fix covers:

- documented MTGJSON archive and checksum filenames;
- settings validation for MTGJSON products and filters;
- a client boundary that always uses validated source URLs and the shared HTTP
  host/redirect policy, while retaining offline mock-client testability;
- a bounded checksum sidecar reader;
- registry/policy validation of reviewed source metadata;
- source-bound, reconstructable raw locators;
- parsing only bytes read from the verified raw archive member;
- deep freezing of permissive MTGJSON DTO values, including forward-compatible
  unknown fields;
- regression tests and documentation/configuration updates.

The fix does not add canonical card resolution, deck/event/combo ingestion,
quarantine semantics, ML, CLI work, live acquisition, or external data.

## Decisions

### Published filenames

The configured base endpoint remains `https://mtgjson.com/api/v5/`. The default
archive extension becomes `.json.zip`, producing for example:

```text
https://mtgjson.com/api/v5/AllPrintings.json.zip
https://mtgjson.com/api/v5/AllPrintings.json.zip.sha256
```

The source configuration and source documentation state these names explicitly.

### HTTP policy boundary

`MTGJSONClient` accepts an optional low-level `httpx.Client` only for local
`MockTransport`/stub tests. It constructs the shared `HttpTransport` itself from
the immutable `SourceSettings`, so callers cannot inject a transport with a
different host allowlist. Every generated URL is validated before the request,
and the returned sanitized endpoint is validated against the same allowlist
before the response is exposed. Request metadata is derived from the same
validated URL and is checked before persistence.

### Settings and reviewed metadata

`MTGJSONSettings.from_source_settings` rejects unknown MTGJSON filter keys,
unknown products, unsupported product fields, and conflicting `files` values in
the top-level and filter locations. A dedicated small checksum limit is stored
in MTGJSON settings and is independent of the general archive download limit.

`SourcePolicy.adapter_configuration` rejects mismatches between adapter source
settings and authoritative registry metadata for review path, approval status,
attribution, raw local storage, and redistribution. The downloader uses the
authoritative historical registry values for the snapshot manifest and never
uses adapter-only terms or policy fields to override them.

### Raw identity and member parsing

`RawLocator` carries `source_id` in addition to snapshot/object/path/member and
JSON-pointer/index/byte-range location data. Staging/provenance contracts reject
source mismatches. The MTGJSON parser rejects verified snapshots whose source is
not `mtgjson`. `parse_member` reads the named member from the verified compressed
raw object; optional caller bytes are accepted only as a comparison and are
rejected when they differ. `parse_archive` compares extracted derived bytes to
the member read from the verified archive before parsing.

### DTO immutability

MTGJSON DTOs keep `extra="allow"` for documented forward-compatible fields, but
unknown nested mappings/sequences are recursively frozen just like declared
fields. Tests assert that nested future fields cannot be mutated and remain
JSON-serializable.

## Error and integrity behavior

- Unsupported settings fail before any request.
- A mock/client response whose final endpoint is outside the source allowlist is
  closed and rejected with a stable MTGJSON client error.
- A checksum sidecar exceeding the dedicated limit fails the snapshot and does
  not publish a checksum object or partial archive object.
- Upstream checksum bytes remain a separate raw object and upstream digest;
  local archive SHA-256 remains the digest of the exact compressed bytes.
- Any archive-member byte mismatch fails closed before DTO parsing.
- Existing raw writer durability, partial-stream, and failed-snapshot guarantees
  remain unchanged.

## Verification

Offline regression tests cover URLs, settings, client endpoint policy, registry
metadata, bounded checksums, source identity, archive-member mismatch, DTO
immutability, and existing raw-byte/checksum behavior. Repository gates cover
focused tests, the complete pytest suite, Ruff, mypy, architecture checks,
fixture/example validation, file-size limits, and `git diff --check`.
