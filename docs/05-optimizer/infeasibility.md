# Infeasibility und Relaxation

## Priorität

1. Legalität niemals relaxen.
2. Must-Exclude niemals relaxen.
3. Must-Include nur nach explizitem Nutzerauftrag relaxen.
4. Budget/Rollen/Landbereiche nur über ein benanntes Relaxationsprofil.

## Diagnose

Der Optimizer prüft Constraints stufenweise und gibt mögliche Konflikte aus, zum Beispiel:

- Must-Include außerhalb Color Identity;
- Budget kleiner als Preis der Pflichtkarten;
- Rollenminimum höher als verfügbare legale Kandidaten;
- Command-Zone-Kombination unter Ruleset unzulässig;
- Collection-only-Pool zu klein.

## Ergebnisstatus

- `OPTIMAL`
- `FEASIBLE`
- `INFEASIBLE`
- `INVALID_REQUEST`
- `SOLVER_LIMIT_REACHED`

Ein `FEASIBLE`-Deck ist legal, aber nicht als bewiesen optimal zu bezeichnen.
