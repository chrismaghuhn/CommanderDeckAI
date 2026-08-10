# Rollen-Taxonomie

Rollen sind versionierte, mehrwertige Features. Eine Karte kann mehrere Rollen besitzen.

## Kernrollen v1

- `land`
- `ramp`
- `card_draw`
- `card_selection`
- `tutor`
- `single_target_removal`
- `stack_interaction`
- `board_wipe`
- `protection`
- `recursion`
- `graveyard_interaction`
- `win_condition`
- `combo_piece`
- `enabler`
- `payoff`
- `mana_sink`
- `token_generation`
- `sacrifice_outlet`
- `stax_or_tax`
- `utility`

## Herkunft

- deterministische Oracle-Text-Regeln;
- strukturierte Keywords/Types;
- Commander-Spellbook-Beziehungen;
- manuell kuratierte Overrides;
- später optional supervised Multi-Label-Modell ohne LLM.

## Vorsicht

Rollen sind keine vollständige Semantik. Ein Rollenminimum ist Nutzer-/Profilconstraint, nicht allgemeine Wahrheit für jedes Deck.
