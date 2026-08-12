# Task 7 Commander Spellbook Review-Fix Design

## Goal

Close the independent Task-7 P1 findings and the small P2 improvements in the
existing `data-foundation` checkout while preserving the raw DTO -> Task-5
staging boundary.

## Scope

The fix covers:

- fail-closed validation of the documented bulk JSON envelope after exact raw
  snapshot finalization;
- verifier-issued raw-snapshot/object evidence for all public parser and
  staging entry points;
- binding of Spellbook source identity, documented endpoint/request lineage,
  product identity, record type, and exact locators;
- strict scalar validation for documented DTO fields, with malformed records
  retained as source values plus parse findings;
- source-owned endpoint/path/contract settings and runtime client binding;
- direct-client enforcement of a three-page maximum for sparse REST reads;
- small local JSON fixtures and focused regression tests.

The fix does not change v1 schemas, canonical card/combo entities, graphs,
CLI behavior, ML/optimization, or Task-1 parity.

## Decisions

### Acquisition policy

Periodic/full Data Foundation acquisition uses the documented bulk JSON
product at `https://json.commanderspellbook.com/variants.json`. The downloader
makes one request, persists the exact response entity through the shared raw
snapshot store, and finalizes the snapshot before any parsing or staging.

The REST `cards` and `variants` contracts remain available for sparse,
interactive reads only. The client rejects pages above three before transport,
so a periodic operation cannot silently become a many-page REST exporter.

### Sparse REST response validation

Sparse REST response parsing still requires a JSON object with the documented
`count`, `next`, `previous`, and `results` fields. Any malformed JSON, shape,
link, or local read fails the derived parse/staging operation rather than
silently ending a sparse read.

The client validates `1 <= page <= settings.max_pages` in both `fetch` and
`request_metadata`, so direct calls cannot bypass the acquisition bound.

### Evidence and identity

`parse_object` remains the primary parser entry point. The compatibility
`parse_bytes` and `parse_payload` entry points require a
`VerifiedSourceSnapshot`, a raw object ID, and a documented contract. They
read the named object from the verified evidence and reject caller bytes or
payloads that do not match it; source IDs, snapshot IDs, and raw paths are
never caller-supplied. The parser verifies that the object ID, object product,
request method/format/endpoint/page, and contract agree before parsing.

The staging mapper requires the same verified snapshot evidence and validates
every record locator against its object bytes before creating staging or audit
rows. This keeps exact JSON-pointer locators while rejecting foreign
snapshots, paths, products, and request lineage.

### Source-owned settings and DTOs

The adapter accepts only the reviewed Spellbook base endpoint,
`/api/{cards,variants}/` products, and `/api` path. Configured contracts may
be a non-empty subset of those two documented contracts, but no other
contracts, endpoint paths, hosts, or source-owned API path can be injected.
Injected downloader clients must be real Commander Spellbook clients whose
settings exactly match the downloader settings.

Documented IDs, text, booleans, and numeric quantities use strict Pydantic
scalar types. Wrong scalar representations produce the existing structural
parse finding and retain the original source value for audit/staging.

## Error behavior

- Sparse REST page-limit failures use stable `SPELLBOOK_PAGE_INVALID` client
  errors before any request. Bulk download failures call the existing writer
  failure path and leave no consumable complete snapshot.
- Evidence failures use stable `INTEGRITY_*` or
  `SPELLBOOK_EVIDENCE_*` parser codes without persisting caller provenance.
- Settings/client mismatches fail before source requests and do not weaken the
  historical approval or current-use policy gates.
- No secret values enter manifests, fixtures, findings, or documentation.

## Verification

Focused tests cover exact bulk bytes, compressed bulk entities, bulk envelope
locators, sparse page bounds, endpoint/settings and injected-client binding,
verified-object byte/payload mismatch, product and request lineage, mapper
evidence requirements, strict scalar failures, exact locators, and the four
small fixture files. Offline repository gates cover the full pytest suite,
Ruff format/check, mypy, architecture/file-size checks, schema/example
validation, fixture consistency, and `git diff --check`.
