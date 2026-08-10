# Kanonische Entitäten

## Card

Spielsemantische Identität über `oracle_id`; Printings werden separat referenziert. Enthält strukturierte Felder, aber keine Source-spezifischen Payloads.

## RulesetSnapshot

- Versions-ID;
- Gültigkeitsdatum;
- Formatregeln;
- Ban-/Sonderlisten;
- Copy-Limit-Ausnahmen;
- Command-Zone-Regeln;
- Quellen/Hashes.

## Deck

- Command Zone als **Set/Liste mehrerer Karten**, nicht einzelnes `commander`-Feld;
- Mainboard als Multiset;
- optional Companion/weitere Zonen;
- Ruleset-Version;
- Source/Provenienz;
- Legalitätsbefund;
- Deckfingerprint.

## Event und Pod

Eventdaten bleiben von Deckdaten getrennt. Ein `PodEntry` verbindet Deck, Sitz, Runde und Ergebnis. Dadurch kann dieselbe Deckliste in mehreren Events auftreten, ohne kopiert zu werden.

## Combo

Combo-ID, Kartenmultiset, Resultat-/Prerequisite-Tags und Source-Provenienz. Combo-Wissen ist ein Feature, keine Legalitätsregel.
