# Use Cases

## UC-01: Teildeck vervollständigen

Input: Command Zone, 40–90 vorhandene Karten, Modus und Constraints.<br>
Output: sortierte Kandidaten mit Score-Komponenten und Ausschlussgründen.

## UC-02: vollständiges Deck optimieren

Input: Command Zone, optionale Must-Includes/Must-Excludes, Rollen- und Budgetprofil.<br>
Output: exakt legales Deck, Solverstatus, harte Constraint-Prüfung und weiche Score-Aufschlüsselung.

## UC-03: bestehendes Deck prüfen

Input: Deckliste und Ruleset-Snapshot.<br>
Output: Legalitätsfehler, Rollenprofil, Kurve, Redundanzen und Modell-Lücken.

## UC-04: Modelle benchmarken

Input: Dataset- und Modellmanifest.<br>
Output: reproduzierbarer Bericht gegen Random-, Popularitäts- und Co-Occurrence-Baselines.

## UC-05: cEDH-Kandidaten reranken

Input: Kandidatendeck und Meta-/Pod-Kontext.<br>
Output: zusätzlicher Outcome-Score mit Unsicherheit; niemals alleiniger Legalitäts- oder Casual-Score.

## UC-06: Forge evaluieren

Input: vollständige Decks, Agentversionen, Seeds und Sitzrotationen.<br>
Output: versionierte Simulationsresultate, die als externe Evidenz gespeichert werden.
