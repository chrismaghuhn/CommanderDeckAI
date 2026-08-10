# Reproduzierbarkeit

## Jeder Run bindet

- Code-Commit;
- Dependency-Lock-Hash;
- Config-Snapshot;
- Inputmanifest-Hashes;
- Feature-/Schema-/Ruleset-Versionen;
- Seeds;
- Hardware-/Threadinformationen;
- Outputchecksums.

## Determinismusstufen

- `STRICT`: Baselines, Datenpipeline, Maskierung, Optimizer-Tie-Break;
- `BEST_EFFORT`: GPU-Training mit dokumentierten nondeterministischen Operationen;
- `EXTERNAL`: Forge/Source-Zugriff, durch Versionen und Rohsnapshots kontrolliert.

## Verifikation

Ein `cda reproduce <run_manifest>`-Use-Case ist später vorgesehen. Bereits M0 definiert die Manifeststruktur, damit Reproduzierbarkeit nicht nachträglich erfunden werden muss.
