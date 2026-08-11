# M4 — Completion Benchmark Freeze

## Ziel

Ein stabiler Benchmark, gegen den Modelle fair verglichen werden können und der früh genug eingefroren wird, um Plattform-Perfektionismus vor dem ersten echten ML-Signal zu verhindern.

## Deliverables

- zeitlicher Standardholdout;
- getrennte High-Data-, Low-Data- und Cold-Commander-Segmente;
- New-Card- und Precon-Segmente;
- eingefrorene Masken und Candidate Pools;
- Leakage-Suite;
- Baseline-Report für B0–B5;
- Benchmarkmanifest und Checksums;
- versioniertes Minimum-Viable-Freeze-Profil;
- preregistriertes Learnability-/Pivot-Gate gemäß `docs/06-evaluation/learnability-pivot-gate.md`.

## Minimum-Viable-Freeze-Trigger

Vor dem Exit von M3 wird ein versioniertes Freeze-Profil committed. Es bindet mindestens:

- `min_qualified_decks` als konkrete Ganzzahl;
- `min_unique_command_zones` als konkrete Ganzzahl;
- konkrete Temporal-Cutoff-Daten und den geforderten abgedeckten Zeitraum;
- konkrete minimale Train-/Validation-/Test-Samplecounts;
- konkrete minimale Samplecounts für alle geschützten Segmente;
- numerische High-/Low-Data-Commander-Grenzen und die Definition von Cold Commander;
- Maskenregime und Candidate-Pool-Policy;
- primäre/sekundäre Metriken und Anti-Collapse-Guardrails;
- G0/G1/G2-Margins und geschützte Segmentgrenzen;
- Bootstrap-/Unsicherheitsmethode;
- Experiment- und Diagnosebudgets.

Qualitative Platzhalter wie „genug Decks“, „ausreichende Coverage“ oder „hinreichend großer Holdout“ erfüllen das Freeze-Profil nicht. M3 kann nicht als bereit für den M4-Freeze gelten, solange die numerischen Mindestwerte nicht committed sind.

Die konkreten Zahlen werden nicht in diesem Milestone-Dokument geraten. Sie werden aus den bis dahin gemessenen Daten abgeleitet und vor dem ersten entscheidenden M4-Validation-Lauf preregistriert. Danach dürfen sie für Benchmark v1 nicht anhand der beobachteten Gate-Ergebnisse verändert werden.

### Ableitungsregel für numerische Mindestwerte

Die Ableitung darf ausschließlich auf **deskriptiven Datenbestands- und Coverage-Statistiken** beruhen, die vor dem ersten entscheidenden M4-Validation-Lauf erzeugt wurden. Zulässige Inputs sind zum Beispiel Deck-/Command-Zone-Counts, Zeitabdeckung, Splitgrößen, Missingness und Segmentgrößen. B0–B6-, DeepSets-, Gate- oder Testmetriken dürfen nicht in die Ableitung der Mindestwerte einfließen.

Für jeden numerischen Mindestwert wird im Freeze-Profil oder einem referenzierten Ableitungsreport festgehalten:

- welche deskriptive Eingangsmetrik verwendet wurde;
- aus welchem Dataset-/Snapshot-Manifest und Hash sie stammt;
- welche deterministische Ableitungsmethode verwendet wurde, zum Beispiel absolute operationale Untergrenze oder explizit definierte Quantil-/Verteilungsregel;
- alle Parameter der Ableitungsmethode;
- Rundungs- und Tie-Break-Regeln;
- der daraus resultierende konkrete Mindestwert.

Eine Formulierung wie „nach Sichtung der Daten festgelegt“ reicht nicht. Die Methode muss so beschrieben sein, dass eine zweite Person aus denselben deskriptiven Inputs denselben Wert berechnen kann. Manuelles Nachjustieren anhand später sichtbarer Baseline-, Validation-, Gate- oder Testresultate ist für Benchmark v1 unzulässig.

Falls sich aus den deskriptiven Daten keine belastbare numerische Mindestbedingung ableiten lässt, wird das als offene Benchmark-Designentscheidung dokumentiert und vor M4 gelöst; es darf nicht während oder nach dem ersten entscheidenden Validation-Lauf improvisiert werden.

### Git-Provenienz des Freeze-Profils

Das Freeze-Profil und sein Ableitungsreport müssen in Git committed sein, **bevor** der erste entscheidende M4-Validation-Lauf gestartet wird.

Der Nachweis basiert nicht nur auf einem Commit-Zeitstempel. Der Commit, der das finale Benchmark-v1-Freeze-Profil enthält, muss ein Ancestor des `git_commit` des ersten entscheidenden Validation-Runs sein. Der Run referenziert zusätzlich mindestens:

- `freeze_profile_commit_sha`;
- Pfad und SHA-256 des Freeze-Profils;
- Pfad und SHA-256 des Ableitungsreports, falls separat;
- die gebundenen Dataset-/Snapshot-Manifest-IDs und -Hashes.

Damit ist im Git-/Run-Verlauf nachweisbar, dass die Schwellen vor dem Ergebnis existierten. Ein späterer Commit darf die Benchmark-v1-Werte nicht rückwirkend ändern; Änderungen erzeugen eine neue Benchmark-/Gate-Version. Ein signierter Tag oder eine zusätzliche Attestation kann später ergänzt werden, ist für v1 aber nicht erforderlich, solange Commit-Ancestry und Run-Provenienz eindeutig sind.

G2 wird erst in M5 ausgeführt, seine Vergleichsregel wird aber bereits mit Benchmark v1 preregistriert. Dadurch kann die Schwelle nicht nach Sichtung der Matrix-Factorization-Ergebnisse verschoben werden.

Sobald diese Mindestbedingungen erfüllt sind, wird Benchmark v1 eingefroren. Zusätzliche Quellen, schönere Reports, größere historische Coverage oder weitere Plattform-Infrastruktur dürfen den Freeze dann nicht verschieben.

TopDeck/Spicerack sind insbesondere **keine Voraussetzung** für M4, wenn der Completion-Benchmark seine preregistrierten Mindestbedingungen ohne diese Quellen erfüllt. Später verfügbare Daten gehen in eine neue Benchmarkversion statt Benchmark v1 rückwirkend zu verändern.

Falls eine Mindestbedingung nicht erfüllt ist, gilt nur Arbeit als M4-blockierend, die diese konkrete Lücke adressiert.

## Learnability-Gate

M4 entscheidet nicht nur, welcher Baseline-Score höher ist. Es prüft stufenweise:

1. `G0a`: schlägt Global Popularity Random Legal belastbar?
2. `G0b`: liefert Commander-spezifische Evidenz gegenüber Global Popularity Zusatznutzen?
3. `G1`: liefert der sichtbare Deckkontext gegenüber Commander-only Ranking zusätzlichen Predictive Value?
4. werden preregistrierte High-/Low-Data-/Cold-Commander-, Temporal-, Long-Tail- oder Anti-Collapse-Guardrails verletzt?

`NDCG@25` ist die primäre v1-Uplift-Metrik, aber ein gutes Overall-NDCG darf keine geschützte Segment- oder Anti-Collapse-Grenze überstimmen. Catalog Coverage, Long-Tail Recall und Novelty-/Popularity-Verteilung laufen verpflichtend als Sekundärdiagnostik mit.

Das M4-Ergebnis wird als `GREEN`, `YELLOW` oder `RED` dokumentiert. `YELLOW` erlaubt pro Benchmark-/Gate-Version genau eine begrenzte, vorher committed Diagnosephase. Danach muss der Zustand auf `GREEN` oder `RED` aufgelöst werden; ein zweites YELLOW-Budget derselben Gate-Version ist nicht zulässig.

Die Gate-Entscheidung ist mechanisch. Ein knapp verfehlter preregistrierter Margin bleibt verfehlt; Reviewer dürfen einen Wert nicht nachträglich als „praktisch GREEN“ freigeben. Eine geänderte Schwelle benötigt eine neue Gate-/Benchmarkversion vor dem nächsten entscheidenden Validation-Lauf.

`RED` blockiert das blinde Hochskalieren zu komplexeren Modellen. G2 wird anschließend in M5 gegen dieselbe preregistrierte Benchmarkversion ergänzt.

## Exit-Kriterien

- keine Splitüberschneidung;
- jede Metrik mit Samplecounts und Unsicherheitsangabe;
- Baselines auf identischen Pools;
- Testset nicht für Tuning verwendet;
- Freeze-Profil enthält konkrete numerische Mindestwerte statt qualitativer Platzhalter;
- numerische Mindestwerte sind über eine reproduzierbare, outcome-blinde Ableitungsregel dokumentiert;
- Freeze-Profil-Commit ist Ancestor des ersten entscheidenden Validation-Run-Commits und wird im Run referenziert;
- Freeze-Profil und G0/G1/G2-Margins vor entscheidenden Validation-Ergebnissen committed;
- B0–B5 gegen die eingefrorene Learnability-Leiter ausgewertet;
- High-/Low-Data-/Cold-Commander- und weitere geschützte Segmente gemäß Freeze-Profil berichtet;
- GREEN/YELLOW/RED-Entscheidung mechanisch mit Segment-/Anti-Collapse-Belegen dokumentiert;
- Dokumentation ausreichend für unabhängige Reproduktion.
