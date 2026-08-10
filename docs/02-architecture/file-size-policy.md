# Dateigrößen- und Wartbarkeitsregeln

Die gewünschte Kleinteiligkeit wird **nach Verantwortungsgrenzen**, nicht nach Zeilenzählerei erreicht.

## Schwellen

- 250 Zeilen: Review-Warnung;
- 400 Zeilen: Split oder ADR-begründete Ausnahme;
- 150 Zeilen für einzelne CLI-Command-Module als Richtwert;
- 300 Zeilen für einzelne Testsuite-Dateien als Richtwert.

## Gute Splits

- `client.py`, `models.py`, `mapper.py`, `settings.py` pro komplexem Source-Adapter;
- `candidate_pool.py`, `core_model.py`, `mana_base.py`, `validator.py` im Optimizer;
- einzelne Metrikfamilien in getrennten Dateien;
- SQL nach Transformation statt eine gigantische Pipeline-SQL.

## Schlechte Splits

- eine triviale Funktion pro Datei;
- viele namenlose `misc`-/`shared`-Pakete;
- zyklische Mini-Module;
- Interfaces ohne zweite Implementierung oder Testnutzen;
- Datentypen duplizieren, nur um Imports zu vermeiden.

Jedes Package besitzt ein kurzes README mit erlaubten Imports, öffentlichen Verträgen und Nicht-Verantwortlichkeiten.
