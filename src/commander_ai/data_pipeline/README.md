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
Die eingefrorene `normalized-snapshot-manifest.v1` bleibt der autoritative Task-5-Output
und wird unverändert erzeugt und gelesen. Seine vollständige Bindung liegt deterministisch
im Content-Digest und in den drei typisierten Parquet-Artefakten: portable Pfade, Hashes,
Byte- und Zeilenzahlen werden gegen das persistierte Run-Manifest, den verifizierten
Raw-Snapshot und jede Datei geprüft. `normalized-snapshot-manifest.v2` bleibt eine separate
optionale strengere Erweiterung und ersetzt v1 nicht.

Die Task-10-Kartenpipeline verarbeitet ausschließlich `OBSERVED`-Stagingzeilen.
`CardCatalogBuilder` erzeugt daraus getrennte Karten-, Face- und Printing-Identitäten
mit einem deterministischen Katalog-Snapshot. Kartenauflösung verwendet nur
Quellen-Identifier, exakte Identifier, Unicode-normalisierte exakte Namen und
dokumentierte Aliase; jeder Versuch bleibt als Auditzeile erhalten, einschließlich
Ambiguitäten und ungelöster Werte. Widersprüchliche Identifier, fehlende
Pflichtfakten und inkonsistente Face-/Printing-Beziehungen werden quarantänisiert.

`CatalogBuildResult.provenance_rows` bewahrt für jede akzeptierte kanonische
Beobachtung den exakten `RawLocator`. Das Schreiben kanonischer Parquet-Zeilen in
die Curated-Schicht benötigt zusätzlich ein verifiziertes, vollständiges Raw-Snapshot
und prüft dessen Objektpfad, Bytes und SHA-256 erneut. Die v1-Kartenverträge bleiben
unverändert; DuckDB und andere lokale Indizes sind aus diesen Artefakten rebuildbar.
