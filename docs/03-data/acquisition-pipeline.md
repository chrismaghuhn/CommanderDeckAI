# Acquisition Pipeline

## Source-Adapter-Aufgaben

1. Anfrageparameter deterministisch erzeugen;
2. Rate Limits und Retry-After respektieren;
3. Antworten unverändert als Raw Objects speichern, soweit erlaubt;
4. Checksums und Response-Metadaten schreiben;
5. Paginierung vollständig und idempotent durchführen;
6. keine Normalisierung im HTTP-Client verstecken;
7. Abrufabbruch als unvollständigen Snapshot markieren.

## Snapshot-ID

```text
{source_id}-{utc_date}-{adapter_version}-{content_prefix}
```

## Idempotenz

Ein abgeschlossener Snapshot wird nie überschrieben. Ein erneuter Abruf erzeugt einen neuen Snapshot, selbst wenn der Inhalt identisch ist; Deduplikation erfolgt über Content Hash und kann Speicher über Hardlinks/Object Store sparen.

## Task 4 acquisition boundary

TopDeck Tournaments v2 requests are currently blocked by the source registry's `PROPOSED`
status. If approved later, configured format filters are expanded into deterministic requests
with one documented singular `format` value each. The exact request-body digest is stored on
each authoritative request record; event, standing, deck, round, table, and player payloads
remain staging records until Task 12 applies canonical observation semantics.

The generic transport exposes raw streamed entity bytes to the snapshot writer. It does
not parse, normalize, decompress, or serialize logical records. HTTP request metadata is
persisted only as a deterministic safe projection: method, sanitized endpoint, API
version, format, and redacted parameters. Authorization headers, cookies, API keys,
credentials, secret query parameters, and unsanitized redirect URLs are not persisted.
The snapshot writer applies the parameter allowlist again at the persistence boundary;
method/API-version/format/terms metadata is normalized or redacted there, including
nested parameter values. An open raw-object writer blocks `COMPLETE`; a streaming or
durability failure closes the writer, removes its temporary object, and leaves the
snapshot `FAILED` or otherwise non-consumable.

Raw-object and manifest files are fsynced before publication. Directory fsync is used
where supported. Windows and explicitly unsupported directory fsync operations use the
safe atomic fallback after file fsync; unexpected fsync errors fail the snapshot before
its `COMPLETE` state becomes consumable.

Every redirect hop and every redirect recorded in an injected response history
must satisfy the configured source host allowlist before persistence. Timeouts,
connection failures, `429`, and retryable server responses use bounded retries and
`Retry-After`; there is no unbounded retry loop. The identifiable user-agent and serial
request pacing are part of the shared transport, not source adapters.
Injected HTTPX clients are forced into manual redirect handling; authorization, cookies,
and API credential headers are stripped when a redirect changes origin, and raw streaming
rejects a truncated `Content-Length` entity.

Compressed MTGJSON-style archives are inspected before extraction. Absolute paths,
drive/UNC names, traversal, backslashes, links, compressed/decompressed size limits,
and unsafe compression ratios are rejected. Windows alternate-data-stream names and
device names are also rejected, and the extraction destination must remain below its
configured root. Extracted files are temporary derived views under that root; the
compressed raw object remains authoritative.

For HTTP responses, `content-encoding` is persisted per raw object as an
allowlisted response-metadata field. The raw entity bytes are finalized and
hashed before any decoding. Bounded `gzip` and `deflate` decoding is used only
for pagination and parsing; unsupported codings and decompressed-size limits
fail closed. Locators resolve against that verified decoded view while the
compressed entity remains the immutable evidence.

## Adapterstruktur

```text
source_name/
├── client.py       # HTTP/Dateizugriff
├── api_models.py   # nur Source-Payloads
├── mapper.py       # Source → Canonical
├── settings.py
├── errors.py
└── README.md
```
## Normalization boundary (Task 5)

Only a `COMPLETE` source snapshot that passes a fresh `RawSnapshotVerifier` check may
be parsed. `INCOMPLETE`, `FAILED`, missing-object, byte-count, object-hash,
snapshot-content-digest, and detached-manifest-digest failures are rejected before
parsing. Historical snapshot approval is not a current-use decision: normalization also
requires the current source policy to allow `normalize`, including takedown/prohibited
checks.

Parsing produces source DTOs and immutable staging records. Every record retains the
source snapshot ID, raw object ID/path, and an exact JSON pointer, record index, or byte
range. Malformed and incomplete values stay in staging and may be written to audit or
quarantine with namespaced findings; they are not coerced into canonical cards, decks,
events, or legality results. All resolution attempts, including ambiguous and
unresolved ones, are retained.
