# Datenaufbewahrung und Exporte

## Lokal

Raw Snapshots werden nur so lange behalten, wie Source-Policy, Reproduzierbarkeit und Speicherbudget es erlauben. Eine Löschung verändert niemals bestehende Manifeste; diese markieren dann den Raw-Status als `purged_by_policy`.

## Öffentliche Artefakte

Ein Export enthält nur Quellen mit explizitem `APPROVED_REDISTRIBUTION`. Für alle anderen Quellen dürfen höchstens Modellgewichte oder aggregierte Statistiken veröffentlicht werden, sofern deren Bedingungen dies erlauben.

## Takedown

Source- und Objekt-IDs müssen erlauben, betroffene Daten aus zukünftigen Datasets auszuschließen. Bereits veröffentlichte Artefakte benötigen eine dokumentierte Deprecation-/Replacement-Strategie.
