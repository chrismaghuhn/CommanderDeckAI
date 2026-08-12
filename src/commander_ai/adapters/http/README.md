# Http

Shared safe HTTP transport primitives only; no source-specific mapping.

Transport uses explicit host allowlists, bounded retries, timeouts, raw entity streaming,
deterministic metadata redaction, and per-hop redirect checks. Redirect handling remains
manual even for injected HTTPX clients; sensitive request headers do not cross origins,
and a declared `Content-Length` must match the raw stream. Redirect counts and request
rates are finite and bounded. Transport failures expose stable sanitized codes without
raw HTTP exception causes. Parsing and decompression belong after raw snapshot
finalization.
