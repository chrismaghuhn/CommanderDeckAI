# JSON-Schemas

Diese Verträge sind die höchste Architekturautorität im Paket.

## Regeln

- Draft 2020-12;
- `additionalProperties: false` für stabile Verträge;
- Version im Dateinamen und Payload;
- Beispiele unter `examples/` müssen in CI validieren;
- Breaking Changes erzeugen v2-Dateien statt stiller Mutation;
- `$id` verwendet absichtlich `example.invalid`, bis das echte Repository eine dauerhafte Schema-URL besitzt.

Domainmodelle dürfen zusätzliche interne Hilfstypen besitzen, aber serialisierte Artefakte müssen einem versionierten Schema entsprechen.
