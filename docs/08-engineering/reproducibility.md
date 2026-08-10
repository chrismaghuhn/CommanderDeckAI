# Reproduzierbarkeit

## Jeder Run bindet

- Code-Commit;
- `git_dirty`; bei `true` zusätzlich `git_worktree_sha256` und ein referenziertes `git_worktree_state`-Artefakt;
- Dependency-Lock-Hash;
- Config-Snapshot;
- generische `inputs` mit IDs, Pfaden und Hashes;
- Feature-/Schema-/Ruleset-Versionen;
- Seeds;
- Hardware-/Threadinformationen;
- Outputchecksums.

`STRICT`-Runs müssen `git_dirty=false` setzen. Dirty-Worktrees bleiben für `BEST_EFFORT` und `EXTERNAL` möglich, wenn ihr vollständiger Zustand gebunden ist.

## Determinismusstufen

- `STRICT`: Baselines, Datenpipeline, Maskierung, Optimizer-Tie-Break;
- `BEST_EFFORT`: GPU-Training mit dokumentierten nondeterministischen Operationen;
- `EXTERNAL`: Forge/Source-Zugriff, durch Versionen und Rohsnapshots kontrolliert.

## Manifest-Digest-Konvention

Das Top-Level-Feld `sha256` ist der SHA-256-Hash der kanonischen UTF-8-JSON-Serialisierung desselben Manifests **ohne** das Top-Level-Feld `sha256`. Die Serialisierung verwendet lexikografisch sortierte Schlüssel, `ensure_ascii=false`, die Trenner `,` und `:` ohne zusätzliche Leerzeichen oder abschließenden Zeilenumbruch. Der resultierende Hash wird als kleingeschriebene Hexadezimalzeichenkette gespeichert. Beim Verifizieren wird genau diese Projektion ohne `sha256` erneut serialisiert und verglichen; verschachtelte Hashfelder bleiben Bestandteil der Eingabe.

## Dirty-Worktree-Zustandsdigest

`git_worktree_sha256` ist **kein** Hash eines normalen `git diff`. Er ist der SHA-256-Hash eines separaten, reproduzierbaren `git-worktree-state.v1`-Datensatzes. Dieser Datensatz enthält genau:

- `schema_version`, `head` mit dem vollständigen Git-Objekt-ID aus `git_commit`;
- `index`: alle `git ls-files --stage`-Einträge mit POSIX-Pfad, Modus, Stage und Git-Objekt-ID; damit ist der staged Zustand einschließlich Konfliktstufen gebunden;
- `worktree`: alle versionierten Pfade und alle nicht ignorierten untracked Dateien. Jeder Eintrag enthält POSIX-Pfad, `kind` (`tracked` oder `untracked`), `state` (`present` oder `deleted`), den Modus bei vorhandenen Dateien und den SHA-256-Hash der tatsächlichen Arbeitsbaumbytes. Damit werden unstaged Änderungen, Löschungen und untracked Dateien erfasst.

`.git`-Metadaten und von der Repository-Ignore-Regel ausgeschlossene Dateien sind nicht Teil dieses Datensatzes; solche ausgeschlossenen Dateien dürfen nicht als reproduzierbare Run-Eingaben verwendet werden. Pfade werden relativ zum Repository, mit `/` und ohne `..`-Segmente gespeichert. Die Arrays werden nach Pfad und anschließend nach den jeweiligen Zustandsfeldern sortiert. Der Datensatz wird als UTF-8-JSON mit lexikografisch sortierten Schlüsseln, `ensure_ascii=false`, keinen zusätzlichen Leerzeichen und keinem abschließenden Zeilenumbruch serialisiert.

Ein Dirty-Run referenziert zusätzlich in `artifacts` ein Artefakt mit `kind: "git_worktree_state"`. Dessen kanonische JSON-Bytes sind die Eingabe für `git_worktree_sha256`; sein `sha256` muss daher mit `git_worktree_sha256` übereinstimmen. Ein bloßer Patch oder ein normaler `git diff` genügt nicht.

## Verifikation

Ein `cda reproduce <run_manifest>`-Use-Case ist später vorgesehen. Bereits M0 definiert die Manifeststruktur in [`schemas/run-manifest.v1.schema.json`](../../schemas/run-manifest.v1.schema.json), damit Reproduzierbarkeit nicht nachträglich erfunden werden muss.
