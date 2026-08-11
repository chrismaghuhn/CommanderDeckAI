# Source Reviews

Diese Dateien sind technische Vorprüfungen auf Basis öffentlich dokumentierter Informationen vom 10. August 2026. Vor Aktivierung werden Terms/Privacy erneut geprüft und das YAML-Review ausgefüllt. Der Status ist ein technisches Risikogate und keine Rechtsgarantie.

Statusbegriffe:

- `APPROVED_LOCAL`: lokaler Abruf/Speicherung ist für die konfigurierte Nutzung freigegeben;
- `APPROVED_REDISTRIBUTION`: lokale Nutzung und öffentliche Weitergabe sind ausdrücklich freigegeben;
- `PROPOSED`: noch nicht freigegeben;
- `REJECTED`: nicht verwenden;
- `PAUSED`: ohne zusätzliche Erlaubnis kein Adapter.

Historische Approval-Metadaten werden getrennt von einer aktuellen Use-/Takedown-Entscheidung gespeichert. Eine spätere `REJECTED`, `PAUSED`, Takedown- oder Prohibition-Entscheidung kann die Verarbeitung eines alten Snapshots blockieren, ohne dessen Provenienz umzuschreiben.

## Reviewed sources

The source-specific records are the review references for activation decisions:

- [MTGJSON](mtgjson.md) — `APPROVED_LOCAL`;
- [Commander Spellbook](commander-spellbook.md) — `APPROVED_LOCAL`;
- [TopDeck.gg](topdeck.md) — `PROPOSED`, credential and terms gate;
- [Spicerack](spicerack.md) — `PROPOSED`, credential and terms gate;
- [Archidekt](archidekt.md) — assessment-only, `RED` for automatic acquisition;
- [Moxfield](moxfield.md) — assessment-only, `RED` for automatic acquisition;
- [EDHREC](edhrec.md) — assessment-only, `RED` for automatic acquisition;
- [cEDH Decklist Database](cedh-decklist-database.md) — assessment-only, `RED`
  for automatic acquisition.

The four assessment-only records deliberately do not authorize bulk retrieval,
undocumented API use, browser automation, or redistribution. A user-provided
export or a separately documented permission path must be reviewed independently.
