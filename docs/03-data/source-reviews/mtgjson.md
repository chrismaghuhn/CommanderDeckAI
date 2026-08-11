# MTGJSON Review

**Status:** APPROVED_LOCAL<br>
**Reviewed:** 2026-08-10<br>
**Downloads:** https://mtgjson.com/downloads/all-files/<br>
**Projektlizenz:** https://github.com/mtgjson/mtgjson

## Geplanter Scope

- `AllDeckFiles` für offizielle Produktdecks;
- `AllPrintings`/Identifier zur Querverknüpfung;
- keine unnötigen Preisdateien im MVP.

## Zugriff und Grenzen

- Zugriff erfolgt über die dokumentierten Bulk-Dateien; die Konfiguration beschränkt Hosts und Dateien explizit.
- Für die lokale Konfiguration ist kein API-Key vorgesehen; Downloadgrößen, Timeout, Rate und Seitenzahl bleiben begrenzt.
- Attribution bleibt erforderlich. Lokale Raw-/Normalised-Speicherung ist konfiguriert; Redistribution ist nicht automatisch freigegeben und wird je Inhalt separat geprüft.
- Der empfohlene Einsatz ist Karten-/Produktprovenienz und die dokumentierten Deckdateien, nicht ein allgemeiner Preis- oder Fremddatenfeed.

## Source-Approval-Gate checklist

1. **Official documentation or permission:** The official downloads page and the MTGJSON repository are the reviewed documentation sources. Public availability and the repository license are not treated as blanket permission for every underlying Magic-related field.
2. **Authentication and rate limits:** The configured bulk path does not require an API key. The configured timeout, download limit, and rate bound apply, and current service guidance must be rechecked before activation.
3. **Attribution:** Attribution to MTGJSON and any applicable upstream content is required in local reports and derived artifacts where the source is used.
4. **Local raw storage:** The configured raw response/archive may be stored locally for the approved local-use path. Exact bytes and the retrieval manifest remain local and immutable; this status does not authorize publication.
5. **Normalized derivations:** Local deterministic derivations may retain the necessary card, printing, product, identifier, and documented deck-provenance fields. Unneeded fields are excluded, and derived artifacts retain source provenance.
6. **Redistribution:** Raw and normalized redistribution is not approved by this review. Each content category requires a separate current review before export.
7. **PII:** Bulk deck or product metadata may contain person-linked or free-text fields. No such fields are necessary for the initial use case; unexpected PII is minimized, quarantined, or excluded from curated output.
8. **Deletion/takedown:** No universal automated deletion guarantee is claimed. A source notice or takedown request pauses affected processing, records the source locator, and triggers removal or quarantine of affected derived outputs after review.
9. **Interval and user agent:** Use explicit, infrequent bulk retrieval rather than polling. The client must identify itself with the project user agent when required and respect current source guidance and configured limits.
10. **Necessary fields/recommended use:** The necessary fields are the configured `AllDeckFiles` and the card/identifier data needed to resolve documented deck and product provenance. Recommended use is local card/deck provenance, not a general price feed or unrestricted content mirror.

## Konfigurierte Bulk-Dateien

Die konfigurierte MTGJSON-v5-Basis ist `https://mtgjson.com/api/v5/`.
Verwendet werden ausschließlich die veröffentlichten Dateinamen
`AllPrintings.json.zip` und `AllPrintings.json.zip.sha256` sowie
`AllDeckFiles.json.zip` und `AllDeckFiles.json.zip.sha256`. Andere Dateinamen,
Suffixe oder Endpunkte sind nicht Teil dieses Reviews. Die Checksum-Seitendatei
wird als eigener Raw-Download unter einem dedizierten Limit von 4096 Bytes
gespeichert; eine fehlende oder deaktivierte Seitendatei blockiert den
unterstützten Erwerb. Sie ersetzt weder die exakten Archivbytes noch deren
lokal berechneten Digest.

## Hinweis

Die MIT-Lizenz des MTGJSON-Projekts wird getrennt von Rechten an zugrunde liegenden Magic-Inhalten behandelt. Attribution und aktuelle Lizenz-/Termsseiten werden im Source-Manifest referenziert. Dies ist keine rechtliche Freigabe.

Der Registry-Eintrag ist die alleinige Quelle für Terms-, Attribution-, lokale
Raw-Speicher- und Redistribution-Metadaten. `APPROVED_REDISTRIBUTION` wird nie
in eine Freigabe umgedeutet, wenn die expliziten Raw-/Derived-Felder
`review_required`, `false` oder `not_approved` enthalten. Fehlende oder
widersprüchliche Metadaten blockieren den Erwerb; der aktuelle Eintrag bleibt
für diesen Checkout `APPROVED_LOCAL` mit `redistribution: review_required`.
