# Adapters

Implementiert Application Ports für Storage, HTTP, Source-APIs und externe Artefakte.

Jeder Source-Adapter bleibt in eigenem Package und besitzt Client, Payloadmodelle, Mapper, Settings, Fehler und README. Source-spezifische Felder dürfen nicht in die Domain durchsickern.
