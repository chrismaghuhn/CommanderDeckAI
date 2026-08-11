# Beispielkonfigurationen

Diese Dateien zeigen den vorgesehenen Zuschnitt. Vor echter Nutzung werden sie in typisierte Settings geladen; unbekannte Felder sind Fehler.

`PROPOSED`, `REVIEWED`, `REJECTED` oder `PAUSED` Sources dürfen nicht synchronisiert werden. Lokaler Sync ist nur für `APPROVED_LOCAL` und `APPROVED_REDISTRIBUTION` erlaubt; Public Export benötigt exakt `APPROVED_REDISTRIBUTION` sowie eine aktuelle Allow-Entscheidung. Secrets werden nur über die angegebenen Environment-Variablen aufgelöst und niemals als Werte konfiguriert.

Source-YAMLs besitzen getrennte Felder für Endpoint-/Host-Allowlist, Credential-Env-Namen, Timeout, Retries, Rate, Seiten-/Downloadlimits und Source-Filter. Dataset-YAMLs besitzen getrennte Filter-, Split- und Near-Duplicate-Policies. Runtime-, Source-, Dataset- und Operation-Felder werden nicht implizit vererbt oder überschrieben.
