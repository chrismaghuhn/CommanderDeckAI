# Architekturtests

Mindestens folgende Regeln werden maschinell geprüft:

- `domain` importiert nur Standardbibliothek und erlaubte Typbibliotheken;
- `application` importiert keine konkreten Adapterbibliotheken;
- `models` importiert kein HTTP-/Source-Package;
- `optimization` importiert keine konkrete Modellklasse;
- `cli` ist die einzige normale Composition Root;
- kein Produktionsmodul importiert `notebooks` oder `tests`;
- keine Dateien namens `utils.py`, `helpers.py`, `common.py` im Kern ohne ADR;
- handgeschriebene `.py`-Dateien über 400 Zeilen schlagen fehl, Ausnahmen stehen in Allowlist mit Begründung.

Diese Tests sind wichtiger als rein kosmetische Paketdiagramme: Sie verhindern schleichenden Architekturverfall.
## Vertrags-Fixtures

Neben der JSON-Schema-Prüfung validiert `scripts/validate_fixture_consistency.py` die referenziellen Beziehungen der Beispielartefakte: Dataset-, Modell-, Ruleset-, Snapshot-, Request- und Result-IDs sowie kompakte Decksummen und Copy-Limits. Dadurch kann ein einzelnes Beispiel nicht unbemerkt von den übrigen Verträgen wegdriften.
