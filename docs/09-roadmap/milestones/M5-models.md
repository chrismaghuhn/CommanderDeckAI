# M5 — Matrix Factorization und DeepSets

## Ziel

Spezialisierte nicht-sprachbasierte Modelle, die Baselines messbar schlagen, ohne Modellkomplexität als Ersatz für fehlendes Learnability-Signal zu verwenden.

## Eintrittskriterium

M4 ist eingefroren und G0/G1 des Learnability-/Pivot-Gates wurden ausgewertet.

- `M4 GREEN`: M5 darf regulär mit B6 beginnen.
- `M4 YELLOW`: M5 darf zunächst nur das vorab begrenzte Diagnose-/B6-Budget verwenden; DeepSets bleibt bis zur dokumentierten Diagnoseentscheidung blockiert.
- `M4 RED`: keine Eskalation zu Matrix-Factorization-/Deep-Learning-Komplexität als bloßer Tuningversuch. Zuerst Dataset/Benchmark oder Aufgabenformulierung korrigieren und versionieren.

Details: `docs/06-evaluation/learnability-pivot-gate.md`.

## Reihenfolge

```text
frozen B4/B5 baseline
  ↓
B6 Weighted Matrix Factorization
  ↓
G2 capacity assessment
  ↓
DeepSets v1, wenn gerechtfertigt
```

Die G2-Regel wurde bereits mit M4 preregistriert und wird nicht nach Sichtung der B6-Ergebnisse verschoben.

B6 wird immer vor DeepSets ausgewertet. Ein schwaches B6 bei starkem G1 darf ein **begrenztes** DeepSets-v1-Experiment als Test nichtlinearer Set-Interaktionen rechtfertigen. Schwaches G1 plus schwaches G2 rechtfertigt dagegen keinen automatischen DeepSets-Start.

G2 kann den aus M4 übernommenen Gate-Zustand aktualisieren. Insbesondere kann ein `YELLOW` nach ausgeschöpftem Diagnosebudget zu `RED` werden.

## Deliverables

- einheitliches `CardRanker`-Protokoll;
- weighted Matrix-Factorization-Baseline;
- G2-Modellkapazitätsbericht;
- DeepSets v1 nur nach Gate-Freigabe;
- Feature-Pipeline und OOV-Fallback;
- Training-/Modelmanifeste;
- Ablations- und Segmentreports;
- Batch-Inference.

## Exit-Kriterien

- messbare Verbesserung gegen B5/B6 gemäß preregistriertem Gate oder dokumentierte Pivot-Entscheidung;
- keine unakzeptierte Coverage-/Long-Tail-Regression;
- Cold-Commander-Bericht;
- Experimentbudget eingehalten und Testset nicht als Tuning-Signal verwendet;
- Modell ohne Netz/Source-Abhängigkeit ladbar;
- `uses_pretrained_language_model=false` verifiziert.

Ein fehlgeschlagenes DeepSets-v1 rechtfertigt nicht automatisch größere Netze, zusätzliche Plattform-Infrastruktur oder Set Transformer. Weitere Komplexität benötigt eine neue dokumentierte Hypothese.
