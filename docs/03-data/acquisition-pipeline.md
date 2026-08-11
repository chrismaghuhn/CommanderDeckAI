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

The generic transport exposes raw streamed entity bytes to the snapshot writer. It does
not parse, normalize, decompress, or serialize logical records. HTTP request metadata is
persisted only as a deterministic safe projection: method, sanitized endpoint, API
version, format, and redacted parameters. Authorization headers, cookies, API keys,
credentials, secret query parameters, and unsanitized redirect URLs are not persisted.
The snapshot writer applies the parameter allowlist again at the persistence boundary;
an open raw-object writer blocks `COMPLETE`, and a published complete manifest cannot be
downgraded by a later writer or error path.

Every redirect hop must satisfy the configured source host allowlist. Timeouts,
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
