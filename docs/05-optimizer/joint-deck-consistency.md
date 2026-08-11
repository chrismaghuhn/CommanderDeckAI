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

Iteratives Repair darf erst bewertet werden, nachdem ein reproduzierbarer one-shot M6-Pfad existiert. Die Kontrollgruppen werden getrennt gehalten:

```text
A0  Ranker raw Top-K
    reine Ranking-Kontrollgruppe; keine vollständige Deckkonstruktion

A1  Ranker + deterministischer greedy legal fill
    billigste vollständige Konstruktionsbaseline

B   Ranker + CP-SAT
    hard constraints, noch ohne kalibrierte Auxiliary Objectives

C   B + kalibrierte Rollen/Pair/Combo-/weitere Auxiliary Objectives

D   C + iteratives Contextual Re-Score/Repair
```

Damit kann getrennt gemessen werden:

```text
A0 -> A1  Effekt trivialer Konstruktion/Legalität
A1 -> B   zusätzlicher Nutzen des Solvers
B  -> C   zusätzlicher Nutzen der Auxiliary Objectives
C  -> D   zusätzlicher Nutzen des iterativen Repairs
```

D wird nur übernommen, wenn es auf eingefrorenen Benchmarks einen relevanten Gewinn gegen C zeigt und die zusätzliche Laufzeit rechtfertigt. Der interne Optimizer-Objective-Wert allein ist kein Deckqualitätsnachweis.

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

Nur die bereits gewählten Karten erneut zu bewerten wäre ein geschlossener Suchraum und könnte schwache lokale Lösungen konservieren. Auch ein Repair-Pool, der ausschließlich aus den global am höchsten gerankten verworfenen Karten besteht, kann einen systematischen Ranker-Fehler fortschreiben.

Deshalb besitzt jedes Repair-Experiment eine versionierte und deterministische `repair_pool_policy`. Sie darf je nach diagnostiziertem Fehler Kandidaten aus mehreren Strata kombinieren, zum Beispiel:

```text
selected_cards
union top_K_overall
union top_K_per_deficient_role
union combo_rescue_candidates
union feasibility_rescue_candidates
union required_constraint_support_candidates
```

Nicht jedes Experiment muss jedes Stratum aktivieren. Die aktivierten Strata, ihre Grenzen, Sortierung und Tie-Breaks sind Teil der versionierten Policy. Ein Rescue-Kandidat muss weiterhin legal und für den jeweiligen Constraint-/Ruleset-Kontext zulässig sein.

Jede Iteration muss ihre Inputs, Score-Snapshots, Candidate-/Repair-Pool-Hashes, `repair_pool_policy`, Optimizer-Konfiguration, strukturellen Deckfingerprints, Änderungen und Laufzeit reproduzierbar referenzieren. Ein bestehender Score-Snapshot wird nie nachträglich verändert.

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

Der Deckzustand wird über den kanonischen strukturellen Deckfingerprint verglichen, nicht über ein bloßes Set ausgewählter `oracle_id`s. Der Fingerprint muss Zonen und Quantitäten gemäß der kanonischen Deckidentität berücksichtigen; dadurch bleiben Copy-Limit-Ausnahmen und unterschiedliche Mengen unterscheidbar.

Für v1 des Repair-Experiments werden Stop-Gründe in fester Präzedenz ausgewertet:

```text
1. if fingerprint_t == fingerprint_(t-1):
       CONVERGED

2. else if fingerprint_t in fingerprints_[0:t-1]:
       CYCLE

3. else if iteration >= max_iterations:
       LIMIT

4. else:
       CONTINUE
```

Damit wird ein unveränderter Deckzustand als `CONVERGED` und nicht zugleich als `CYCLE` klassifiziert. Ebenso hat echte Konvergenz auf der letzten erlaubten Iteration Vorrang vor `LIMIT`. `LIMIT` ist kein Konvergenznachweis.

Fingerprint-basierte Cycle Detection setzt in v1 eine deterministische, history-unabhängige Transition voraus: Derselbe kanonische Deckfingerprint muss unter demselben Modell, derselben versionierten `repair_pool_policy`, denselben Constraints und derselben Optimizer-Konfiguration wieder denselben nächsten Suchzustand erzeugen. Falls später eine history-abhängige Repair-Policy eingeführt wird, muss der Cycle-State-Key mindestens um den relevanten Policy-Zustand und den Repair-Pool-Hash erweitert werden; der Deckfingerprint allein reicht dann nicht mehr.

Eine Epsilon-Regel über den jeweils aktuellen Solver-Objective ist in v1 ausdrücklich **nicht** zulässig: Durch das Contextual Re-Scoring verändert sich zwischen Iterationen die zugrunde liegende Objective-Funktion. Objective-Werte aus zwei unterschiedlich gescorten Iterationen sind daher nicht automatisch vergleichbar.

Eine spätere Epsilon-Regel darf nur eingeführt werden, wenn eine konstante, versionierte und iterationsübergreifend vergleichbare Evaluationsfunktion definiert ist. Diese Evaluationsfunktion muss von den jeweils neu berechneten Optimizer-Scores semantisch getrennt sein.

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
- Optimizer-Objective-Komponenten, ohne Cross-Iteration-Vergleichbarkeit zu unterstellen;
- strukturelle Deckfingerprints und Karten-/Mengenänderungen pro Iteration;
- Zyklus-/Konvergenzrate und Stop-Grund;
- Laufzeit und Solverbudget;
- später separat cEDH-Outcome- und Forge-Evidenz.

## Aktivierungsregel

Iteratives Repair wird nicht aus Architekturästhetik aktiviert. Es muss einen gemessenen Fehler des one-shot Ranker+CP-SAT-Pfads adressieren, etwa relevante Kontextdrift, Rollenredundanz oder systematische lokale Auswahlfehler, und diesen Fehler auf eingefrorenen Benchmarks besser lösen als die einfachere Baseline.
