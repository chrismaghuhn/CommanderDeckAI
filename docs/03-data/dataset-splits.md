# Dataset-Splits und Leakage-Kontrolle

## Standard-Split

Zeitbasiert mit Gruppenbindung:

- Train: ältere Deck-/Eventdaten;
- Validation: späteres Zeitfenster;
- Test: jüngstes eingefrorenes Zeitfenster.

Alle Deckrevisionen, exakten Duplikate und Near-Duplicate-Cluster werden gemeinsam zugewiesen.

## Zusätzliche Testsets

- `cold_commander`: Command-Zone-Kombinationen nicht im Training;
- `low_data_commander`: sehr wenige Trainingsdecks;
- `new_card_window`: Karten nach dem Trainings-Cutoff;
- `precon_holdout`: vollständige offizielle Produkte;
- `cedh_temporal`: spätere Turniere, nach Event gruppiert.

## Verboten

- zufälliger Row-Split über Deckkarten;
- dieselbe Deckrevision in mehreren Splits;
- Eventrunden desselben Events über Train/Test verteilen;
- Features verwenden, die nach dem Beobachtungszeitpunkt entstanden sind;
- aktuelles EDHREC-/Meta-Feature an historische Samples hängen.

## Forward-only-Gruppenpromotion

Bei Completion-Datasets werden zunächst zeitbasierte Provisional-Splits vergeben.
Danach werden exakte Fingerprints, Source-Revisionen und die versionierten
Near-Duplicate-Cluster gebildet. Eine Gruppe wird in den spätesten Provisional-Split
verschoben, den eines ihrer Mitglieder erreicht; sie wird nie in einen älteren Split
zurückverschoben. Ein Cluster mit `TRAIN`, `TRAIN`, `TEST` wird deshalb vollständig
`TEST`. Algorithmus, Version, Schwelle und Promotion-Regel gehören in das
Dataset-Manifest.

Outcome-Datasets gruppieren vollständige Events statt wiederholte CanonicalDecks
global zu sperren. Strenge Zusatzbenchmarks können kalte Fingerprints, Command-Zone-
Kombinationen und Low-Data-Commander separat ausweisen.

## Task-13-Artefakte

`DatasetSettings` verlangt für die implementierten Split-Builder explizite
timezone-aware `train_until`- und `validation_until`-Cutoffs. Der
`dataset-manifest.v2` bindet zusätzlich `dataset_kind`, Konfigurationsversion,
Split-/Exclusion-Version, Near-Duplicate-Algorithmus, Version und Schwelle,
Input-Manifest-Hashes, Ausschlüsse, Counts sowie Parquet- und Inhalts-Digests.

Der Dataset-Builder schreibt eine immutable Curated-Projektion unter
`datasets/{dataset_id}/` und ein kanonisch serialisiertes Manifest. `inspect`
prüft Manifest-Digest, Existenz, Hash und Row-Count jedes Outputs. Die
Curated-Payload maskiert bekannte Player-/Account-Felder; Audit- und
Quarantine-Informationen bleiben außerhalb dieses Trainingsartefakts.
