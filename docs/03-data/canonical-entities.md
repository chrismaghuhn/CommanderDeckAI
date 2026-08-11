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

Historische Evaluation wählt den Snapshot ausschließlich über `effective_from` und
`effective_until`. Wenn kein eindeutiger Snapshot anwendbar ist, bleibt der
Legalitätsstatus `unknown`; die aktuelle Banlist wird nicht ersatzweise verwendet.

## Deck

- Command Zone als **Set/Liste mehrerer Karten**, nicht einzelnes `commander`-Feld;
- Mainboard als Multiset;
- optional Companion/weitere Zonen;
- Source/Provenienz;
- Deckfingerprint.

Legalitäts- und Qualitätsbefunde werden als separate, ruleset-/policy-spezifische
Evaluationen gespeichert und verändern die strukturelle Deckidentität nicht.

`canonical_deck_id` ist der deterministische Struktur-Fingerprint der Formatfamilie
`commander`. Ruleset-Version, Quelle, Spieler, Event, Zeitpunkt und Evaluationen sind
keine Bestandteile dieser Identität. Partner-/Background-Rollen werden als
Source-Evidenz bewahrt; die Ruleset-Validierung bleibt für ihre Legalität autoritativ.

## Event und Pod

Eventdaten bleiben von Deckdaten getrennt. Event-Deck-Beobachtungen enthalten
Finalplatzierung und aggregierte Ergebnisse; ein `PodEntry` verbindet Deck, Sitz,
Runde und Ergebnis. Alle Sitze bleiben unter einer Pod-ID gruppiert, damit keine
synthetischen 1v1-Matches entstehen. Dadurch kann dieselbe Deckliste in mehreren
Events auftreten, ohne kopiert zu werden.

Der Event-Header wird als `event.v1` persistiert, die gruppierte Pod-Projektion als
expliziter Nachfolger `pod.v2`; beide bewahren den exakten Raw-Locator. Externe
Event-, Pod- und Combo-IDs werden mit RFC-3986-kodierten Quellsegmenten namespaced.
Event-Header und Finalstandings müssen aus derselben Quelle und demselben Snapshot
stammen, bevor eine Beobachtung kuratiert wird.

## Combo

Combo-ID, Kartenmultiset, Resultat-/Prerequisite-Tags und Source-Provenienz. Combo-Wissen ist ein Feature, keine Legalitätsregel.
