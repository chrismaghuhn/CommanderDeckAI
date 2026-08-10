# CP-SAT-Modell

## Variablen

- `x_i ∈ {0,1}`: Kandidatenkarte gewählt;
- `q_i`: Menge, nur für Karten mit erlaubter Mehrfachzahl/Basic Lands;
- `z_ij ∈ {0,1}`: ausgewählte relevante Kartenpaarung;
- Rollen-/Kurven-Slackvariablen nur für explizit weiche Ziele.

## Kernconstraints

```text
sum quantities + command_zone_count = required_total
color_identity(i) ⊆ commander_identity
quantity(i) ≤ copy_limit(i, ruleset)
must_include(i) = 1
must_exclude(i) = 0
role_min[r] ≤ sum role(i,r)*x_i ≤ role_max[r]
price_sum ≤ budget
```

## Integer-Scores

CP-SAT arbeitet mit Integerkoeffizienten. Fließkomma-Scores werden über eine versionierte Skalierung quantisiert. Rundungsfehler und Wertebereich werden getestet.

## Determinismus

Solverparameter, Zeit-/Konfliktgrenzen, Seed und Threadzahl stehen im Resultmanifest. Bei mehreren optimalen Lösungen sorgt ein stabiler sekundärer Tie-Breaker für reproduzierbare Auswahl.
