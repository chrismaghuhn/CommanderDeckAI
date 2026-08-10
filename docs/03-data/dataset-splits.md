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
