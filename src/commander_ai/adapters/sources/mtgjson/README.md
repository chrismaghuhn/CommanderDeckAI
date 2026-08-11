# MTGJSON adapter

The adapter consumes only the configured `AllPrintings` and `AllDeckFiles`
bulk products from the documented MTGJSON file server. The source review and
current-use policy remain the authority for local acquisition; this package
does not authorize a source by itself.

```text
settings.py    source-owned product, archive, checksum, and URL settings
client.py      configured requests over shared bounded HTTP transport
downloader.py  policy-gated immutable raw snapshot acquisition
dto.py         permissive MTGJSON card, face, set, file, and deck-product DTOs
parser.py      verified archive extraction and exact member/JSON-pointer records
staging.py     Task-5 SourceRecordDTO/StagingRecord mapping only
```

The compressed archive is the authoritative raw object. Extracted JSON is a
derived view and is never substituted for the archive. A published SHA-256
sidecar is retained separately; `objects[].sha256` always denotes the locally
computed digest of the exact downloaded archive bytes, while
`objects[].upstream_sha256` and `checksum_verification_status` retain the
upstream value and comparison result.

The reviewed documentation is the [MTGJSON all-files page](https://www.mtgjson.com/downloads/all-files/)
and the [MTGJSON FAQ checksum guidance](https://www.mtgjson.com/faq/). The
adapter does not infer undocumented endpoints, collapse printings or faces,
or create canonical cards/resolution records.
