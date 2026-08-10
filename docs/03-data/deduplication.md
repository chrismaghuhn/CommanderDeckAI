# Deduplikation

## Stufen

1. **Exact source object:** identischer Source-Key und Payload-Hash.
2. **Exact deck:** identischer `deck_fingerprint_v1`.
3. **Revision group:** gleiche externe Deck-ID über Zeit.
4. **Near duplicate:** hohe Jaccard-Ähnlichkeit innerhalb gleicher Command Zone.
5. **Precon clone:** Nähe zu offiziellen Precons gesondert markieren.

## Trainingsregel

Alle Revisionen und Near-Duplicate-Cluster bleiben im selben Split. Ein Deck darf nicht als fast identischer Klon im Training und Test auftauchen.

## Keine aggressive Löschung

Deduplikation schreibt Cluster- und Repräsentanten-IDs. Rohdaten werden nicht stillschweigend entfernt. Outcome-Daten dürfen wiederholte Eventeinträge behalten, weil Ergebnis und Zeitpunkt eigenständige Beobachtungen sind.
