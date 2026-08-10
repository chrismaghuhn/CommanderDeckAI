# Completion-Dataset

## Sample-Erzeugung

Für jedes qualitätsgeprüfte Deck werden mehrere deterministische Masken erzeugt. Der Seed wird aus Deckfingerprint, Datasetversion und Maskenindex abgeleitet.

## Maskentypen

- zufällig 10–40 % der Nicht-Command-Zone-Karten;
- `late_build`: nur 10–20 Slots fehlen;
- `early_build`: großer Teil fehlt;
- `role_hole`: gezielt eine Rollenfamilie maskieren;
- `combo_hole`: ein Combo-Stück maskieren, ohne Testlabels aus externem Wissen zu leaken;
- `land_hole`: separat, erst ab Mana-Base-Milestone.

## Positive Labels

Die tatsächlich maskierten Karten. Bei mehreren plausiblen Alternativen bleibt das Label unvollständig; deshalb sind Completion-Metriken notwendig, aber nicht hinreichend für echte Deckqualität.

## Kandidatenpool

Der Pool wird aus dem **zeitlich passenden** Card-/Ruleset-Snapshot erzeugt. Testkarten, die damals noch nicht existierten oder illegal waren, dürfen nicht als Negatives erscheinen.

## Samplegewicht

Near-Duplicate-Cluster, Precon-Klone und massenhaft replizierte Staples werden gewichtet, damit ein einzelnes Listenmuster das Training nicht dominiert.
