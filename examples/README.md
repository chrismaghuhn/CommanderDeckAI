# Beispiele

Die Beispiele sind **synthetisch** und enthalten absichtlich keine echten vollständigen Decklisten. UUIDs und Hashes dienen der Vertragsvalidierung.

Kompakte Deck-Beispiele verwenden die in `ruleset.v1.json` unter `unlimited_copy_oracle_ids` eingetragene Fixture-Karte. Dadurch bleiben die Dateien klein, ohne in den Beispielen 99 einzelne Kartenreferenzen zu duplizieren. Diese Fixture-Karte ist kein Anspruch auf eine reale Kartenidentität.

Die JSON-Schemas prüfen Struktur und elementare Wertebereiche. Commander-Legalität, Color Identity und Command-Zone-Sonderregeln werden zusätzlich durch den unabhängigen Domain-Validator geprüft; sie gehören nicht vollständig in JSON Schema.

In CI werden alle JSON-Dateien gegen das gleichnamige v1-Schema geprüft.
