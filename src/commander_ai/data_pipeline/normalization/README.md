# Normalization

Canonical mappers and normalized snapshot builders.

The normalization input must be a `COMPLETE` raw snapshot whose manifest, objects,
content digest, and detached digest passed `RawSnapshotVerifier`, plus an independent
current-use policy decision. The Task-5 application coordinator performs these gates;
source values and failed observations remain in staging/audit/quarantine.
