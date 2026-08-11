# Joint Deck Consistency und iteratives Repair

## Status

Experimenteller Gate nach M6. Kein verpflichtender Bestandteil des v1-Optimizers.

## Problem

Der Ranker bewertet Kandidaten gegen einen festen sichtbaren Deckkontext:

```text
s(card | command_zone, visible_deck, profile, ruleset)
```

Der Optimizer kann danach viele Karten gleichzeitig auswählen. Dadurch kann sich der relevante Deckkontext ändern, obwohl alle Kandidatenscores aus demselben unveränderlichen Score-Snapshot stammen. Zwei Karten können einzeln hoch bewertet sein, zusammen aber dieselbe Rolle überfüllen oder andere Karten verdrängen.

Pair-Synergy, Rollenabdeckung und Combo-Ziele reduzieren dieses Risiko, ersetzen aber keine vollständige erneute Kontextbewertung des vorgeschlagenen Decks.

## Semantische Grenze

Completion-Qualität ist nicht gleich Deckqualität:

```text
Recommendation quality
!= Construction quality
!= Gameplay strength
```

M5 lernt primär, welche Karten unter einem Deckkontext in realen Decklisten plausibel sind. Eine Verbesserung von Recall/NDCG darf nicht als gleich große Verbesserung von Deckstärke, Winrate oder Spielerpräferenz interpretiert werden.

M6 erzeugt legale und constraint-konforme Decks. M7/M8 liefern erst zusätzliche Outcome- beziehungsweise Gameplay-Evidenz.

## Baseline vor Repair

Iteratives Repair darf erst bewertet werden, nachdem ein reproduzierbarer one-shot M6-Pfad existiert. Mindestens folgende Ablation-Ladder soll vergleichbar sein:

```text
A  Ranker Top-K / einfache Auswahl
B  Ranker + CP-SAT
C  Ranker + CP-SAT + kalibrierte Rollen/Pair/Combo-Ziele
D  C + iteratives Contextual Re-Score/Repair
```

D wird nur übernommen, wenn es auf eingefrorenen Benchmarks einen relevanten Gewinn gegen C zeigt und die zusätzliche Laufzeit rechtfertigt.

## Experimenteller Repair-Loop

Ein möglicher deterministischer Ablauf ist:

```text
Partial Deck
  -> Ranker Score Snapshot
  -> CP-SAT
  -> Proposed Deck
  -> Contextual Re-Score
  -> Repair Pool
  -> CP-SAT
  -> convergence / cycle / iteration limit
```

Für bereits ausgewählte Karte `X` wird bevorzugt Leave-One-Out bewertet:

```text
score(X | ProposedDeck - X)
```

Zusätzlich wird ein deterministischer Challenger-Pool aus nicht gewählten, zuvor hoch gerankten legalen Karten erneut bewertet. Nur die bereits gewählten Karten zu re-scoring wäre ein geschlossener Suchraum und könnte schwache lokale Lösungen konservieren.

Jede Iteration muss ihre Inputs, Score-Snapshots, Candidate-/Repair-Pool-Hashes, Optimizer-Konfiguration, Änderungen und Laufzeit reproduzierbar referenzieren. Ein bestehender Score-Snapshot wird nie nachträglich verändert.

## DeepSets und Leave-One-Out

Bei additivem DeepSets-Pooling kann Leave-One-Out günstig sein:

```text
deck_context = sum(phi(card))
context_without_x = deck_context - phi(x)
```

Das ist eine Implementierungsoptimierung, keine semantische Garantie. Sie gilt nur, wenn die konkrete Modellarchitektur diese Zerlegung tatsächlich erlaubt.

## Training-Distribution und OOD-Risiko

Ein Completion-Modell, das überwiegend stark maskierte Decks sieht, ist nicht automatisch für `ProposedDeck - X` mit nahezu vollständigen Decks kalibriert.

Bevor Leave-One-Out-Scores als Repair-Signal verwendet werden, muss deshalb mindestens eines gelten:

- das Training enthält explizite Late-Stage-/Repair-Masken, einschließlich sehr kleiner Masken;
- oder die Near-Complete-Performance wird separat gemessen und als ausreichend belegt.

Andernfalls wird der Repair-Pfad als Out-of-Distribution-Experiment markiert und darf nicht allein aufgrund interner Scores zum Default werden.

## Konvergenz und Zyklen

Der Loop benötigt deterministische Stop-Regeln. Beispiele:

- ausgewähltes Kartenset unverändert;
- Verbesserung unter einer versionierten Epsilon-Schwelle;
- erkannter Zyklus, zum Beispiel `Deck A -> Deck B -> Deck A`;
- konfiguriertes maximales Iterationslimit.

Ein Iterationslimit allein gilt nicht als Konvergenznachweis.

## Doppelzählung von Synergie

DeepSets kann Card-Card-Zusammenhänge implizit aus Deckdaten lernen. CP-SAT kann dieselbe Beziehung zusätzlich über Pair-Synergy oder Spellbook-Combo-Boni belohnen. Diese Signale dürfen nicht ungeprüft mehrfach dieselbe Evidenz verstärken.

Deshalb sind Ablations erforderlich, mindestens:

```text
ranker
ranker + roles
ranker + pair
ranker + combo
ranker + pair + combo + roles
```

Gewichte bleiben versionierte, kalibrierte Optimizer-Konfiguration. Auxiliary Objectives dürfen weder Legalität noch harte Nutzerconstraints überschreiben.

## Messgrößen

Der Repair-Pfad wird nicht nur mit Completion-Metriken bewertet. Mindestens berichten:

- Completion Recall/NDCG als Recommendation-Signal;
- Legalität und harte Constraint-Erfüllung;
- Rollenüberdeckung und Rollenlücken;
- Pair-/Combo-Metriken ohne Doppelzählungsannahme;
- Deckdiversität;
- Optimizer-Objective-Komponenten;
- Kartenwechsel pro Iteration und Stabilität;
- Zyklus-/Konvergenzrate;
- Laufzeit und Solverbudget;
- später separat cEDH-Outcome- und Forge-Evidenz.

## Aktivierungsregel

Iteratives Repair wird nicht aus Architekturästhetik aktiviert. Es muss einen gemessenen Fehler des one-shot Ranker+CP-SAT-Pfads adressieren, etwa relevante Kontextdrift, Rollenredundanz oder systematische lokale Auswahlfehler, und diesen Fehler auf eingefrorenen Benchmarks besser lösen als die einfachere Baseline.
