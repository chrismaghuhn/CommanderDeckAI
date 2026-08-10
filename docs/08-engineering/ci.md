# CI

## PR-Pipeline

1. Dependency-Lock-Konsistenz;
2. Format/Lint;
3. Typprüfung;
4. Unit- und Contracttests;
5. Schema-Beispielvalidierung;
6. Architektur-Importtest;
7. Tiny E2E;
8. Secret-/Large-File-Prüfung;
9. `git diff --check`-äquivalente Whitespace-Prüfung.

## Nightly/Manuell

- Live-Source-Contract-Smokes mit Secrets;
- größere Dataset-Quality-Suite;
- Modell-Smoke auf repräsentativem Sample;
- OR-Tools-Stresscases;
- Forge-Bridge-Smoke, sofern Umgebung vorhanden.

## Release

Artefaktmanifeste, Benchmarkreport und Checksums werden als Releaseassets erzeugt. Fremddaten werden nur bei expliziter Redistribution-Freigabe angehängt.
## Supply-Chain-Pinning

- GitHub Actions werden im Blueprint auf vollständige Commit-SHAs gepinnt;
- die lesbare Release-Version bleibt als Kommentar erhalten;
- `uv` ist in `pyproject.toml` und CI auf dieselbe Version gepinnt;
- Python 3.12 steht zusätzlich in `.python-version`;
- Abhängigkeiten werden erst nach Commit des erzeugten `uv.lock` mit `--locked` installiert.
