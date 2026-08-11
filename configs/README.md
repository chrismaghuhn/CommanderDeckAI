# Beispielkonfigurationen

`sources/permission-gated.yaml` is loaded as a typed assessment-only catalog. Its `PROPOSED` and `PAUSED` entries reuse the `SourceApprovalStatus` contract but cannot authorize acquisition; enabling a source requires a separate source-registry and review entry.

Diese Dateien zeigen den vorgesehenen Zuschnitt. Vor echter Nutzung werden sie in typisierte Settings geladen; unbekannte Felder sind Fehler.

`PROPOSED`, `REVIEWED`, `REJECTED` oder `PAUSED` Sources dürfen nicht synchronisiert werden. Lokaler Sync ist nur für `APPROVED_LOCAL` und `APPROVED_REDISTRIBUTION` erlaubt; Public Export benötigt exakt `APPROVED_REDISTRIBUTION` sowie eine aktuelle Allow-Entscheidung. Secrets werden nur über die angegebenen Environment-Variablen aufgelöst und niemals als Werte konfiguriert.

Source-YAMLs besitzen getrennte Felder für Endpoint-/Host-Allowlist, Credential-Env-Namen, Timeout, Retries, Rate, Seiten-/Downloadlimits und Source-Filter. Dataset-YAMLs besitzen getrennte Filter-, Split- und Near-Duplicate-Policies. Runtime-, Source-, Dataset- und Operation-Felder werden nicht implizit vererbt oder überschrieben.

The CLI source-sync boundary is a full typed `SourceRegistry` file. The small
source files in `configs/sources/` are not silently upgraded into registry
entries, because historical approval and current-use/takedown decisions must be
explicit. A missing or incomplete registry fails closed with a stable policy or
configuration error. Runtime roots are supplied through `RuntimeConfig`; the
default CLI roots are repository-local `data/` and `artifacts/`. Persisted config
snapshots use portable root references and never contain resolved credentials.
