# Score-Kalibrierung

Ranker-, Synergie-, Rollen- und Preiswerte haben unterschiedliche Skalen.

## Vorgehen

- jede Komponente auf Validation-Daten untersuchen;
- robuste Quantil-/Z- oder Min-Max-Skalierung mit eingefrorenen Parametern;
- Ausreißergrenzen dokumentieren;
- Integerquantisierung für CP-SAT testen;
- Gewichtssensitivität über Profil-Sweeps messen.

## Kein versteckter Gesamtwert

Optimizer-Ausgabe enthält Rohwert, skalierten Wert, Gewicht und Beitrag je Komponente. Dadurch kann ein Nutzer erkennen, ob ein Deck durch Popularität, Combo oder Rollenbalance getrieben wurde.
