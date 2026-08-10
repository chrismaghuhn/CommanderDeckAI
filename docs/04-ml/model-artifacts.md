# Modellartefakte

```text
artifacts/models/{model_name}/{run_id}/
├── manifest.json
├── config.resolved.yaml
├── dataset.manifest.json
├── feature_spec.json
├── state_dict.pt
├── metrics.validation.json
├── metrics.test.json           # erst nach finaler Evaluation
├── calibration.json            # optional
└── environment.txt
```

## Kompatibilitätsfelder

- Modellarchitekturversion;
- Input-Schemaversion;
- Card-Snapshot-Kompatibilität;
- Feature-Spec-Version;
- Ruleset-Familie;
- `uses_pretrained_language_model: false`;
- Code-Commit und Lock-Hash.

Ein Loader verweigert stille Teilkompatibilität. Fehlende Features oder unbekannte IDs benötigen explizite Fallback-Policy.
