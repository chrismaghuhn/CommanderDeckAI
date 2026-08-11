# Config

Typisierte Loader für kleine YAML-Dateien. Runtime-, Source-, Dataset- und Operation-Konfigurationen sind getrennt und lehnen unbekannte Felder ab. Secrets kommen aus Environment/Secret Store; persistiert werden nur Env-Namen und redigierte, aufgelöste Snapshots. Source-Registry und current-use policy halten historische Approval-Metadaten von späteren Takedown-/Nutzungsentscheidungen getrennt.
