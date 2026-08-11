# Commander Spellbook Review

**Status:** APPROVED_LOCAL<br>
**Reviewed:** 2026-08-10<br>
**Backend:** https://github.com/SpaceCowMedia/commander-spellbook-backend<br>
**Docs:** https://spacecowmedia.github.io/commander-spellbook-backend/

## Geplanter Scope

Combo-IDs, beteiligte Karten, Preconditions, Resultat-/Feature-Tags und Variantbeziehungen.

## Zugriff und Grenzen

- Verwendet werden nur dokumentierte Read-Verträge oder ein ausdrücklich freigegebener Export; undokumentiertes Scraping bleibt ausgeschlossen.
- Die konfigurierte API-Host-Allowlist, Timeout-, Retry-, Rate-, Seiten- und Downloadgrenze gilt vor jeder späteren Adapterverdrahtung.
- Attribution bleibt erforderlich. Lokale Raw-/Normalised-Speicherung ist konfiguriert; Redistribution von Fremdinhalten bleibt einer separaten Inhaltsprüfung unterworfen.
- Empfohlener Einsatz sind Combo-/Kartenbeziehungen als Feature-Fakten, nicht als automatische Legalitäts- oder Gameplay-Garantie.

## Nicht tun

- Combo-Daten als garantierte Gameplay-Wahrheit behandeln;
- externe Kartendaten duplizieren, wenn Oracle-IDs verknüpft werden können;
- Combo-Frequenz ohne Deck-/Zeitkontext als Stärke interpretieren.

## Lizenz

Backend ist als MIT dokumentiert; konkrete API-/Datenattribution und mögliche Fremdinhalte werden vor Redistribution geprüft. Dies ist keine rechtliche Freigabe.
