# Http

Shared safe HTTP transport primitives only; no source-specific mapping.

Transport uses explicit host allowlists, bounded retries, timeouts, raw entity streaming,
deterministic metadata redaction, and per-hop redirect checks. Parsing and decompression
belong after raw snapshot finalization.
