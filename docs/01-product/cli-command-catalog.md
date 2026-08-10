# CLI Command Catalog

Die CLI ist eine dünne Composition Root. Jeder Befehl ruft genau einen Application Use Case auf.

```text
cda doctor
cda source list
cda source review <source>
cda source sync <source> --config ...
cda data normalize <snapshot-id>
cda data validate <normalized-snapshot-id>
cda dataset build --config configs/datasets/completion-v1.yaml
cda dataset inspect <dataset-id>
cda benchmark run <model-id> <dataset-id>
cda train matrix-factorization --config ...
cda train deepsets --config ...
cda rank --request request.json
cda optimize --request optimization.json
cda deck validate deck.json
cda forge enqueue request.json
cda forge collect <request-id>
cda artifact verify <manifest.json>
```

## Ausgabeformat

- interaktive Standardausgabe ist knapp und menschenlesbar;
- `--json` liefert stabile maschinenlesbare Events;
- lange Reports werden als Artefaktdatei geschrieben;
- Fehler liefern stabilen Exitcode und `error_code`;
- kein Befehl startet versteckt einen anderen teuren Job.

## Exitcodes v1

- `0`: Erfolg;
- `2`: ungültige Eingabe/Config;
- `3`: Source-/Zugriffsgate;
- `4`: Datenqualitätsfehler;
- `5`: Modell-/Artefaktinkompatibilität;
- `6`: Optimizer infeasible;
- `7`: externer Forge-/Source-Fehler;
- `10`: interner unerwarteter Fehler.
