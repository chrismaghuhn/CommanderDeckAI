# Data Pipeline

Normalisierung, Qualitätsregeln, Deduplikation, zeitliche Gruppensplits und Dataset-Builder.

Transformationen lesen immutable Inputs und schreiben neue Manifeste. Kein Training und keine Live-API-Aufrufe in Dataset-Buildern.

Task 5 hält die Grenze `raw object -> parse/structural validation -> staging ->
resolution -> canonical/curated` explizit. Staging enthält source-nahe Werte und
einen `RawLocator`; es erzwingt keine Domain- oder Commander-Legalitätsinvarianten.
Parse-, Integritäts-, Resolution-, Legalitäts- und Qualitätsbefunde haben getrennte
Namespaces. Audit- und Quarantänezeilen werden behalten und nie als curated
ausgegeben. Parquet und das versionierte Normalized-Snapshot-Manifest sind die
autoritativen normalisierten Artefakte; SQL/DuckDB bleibt rebuildbarer lokaler Index.
Die eingefrorene v1 bleibt unverändert. Für die vollständige Task-5-Bindung verwendet
die Persistenz die versionierte v2-Erweiterung: Sie bindet normalisierte, Audit- und
Quarantäne-Parquet-Dateien jeweils mit portablem Pfad, Bytezahl, Hash und Zeilenzahl
und wird vor Verwendung gegen Run-Manifest, Raw-Snapshot und alle Dateien verifiziert.
