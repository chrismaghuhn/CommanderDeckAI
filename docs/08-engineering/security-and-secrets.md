# Secrets und sichere Adapter

- API-Keys nur aus Environment/Secret Store;
- Logs redigieren Authorization-/Cookie-Header;
- HTTP-Clients erhalten explizite Host-Allowlist;
- Redirects zu unbekannten Hosts standardmäßig ablehnen;
- Source-Downloads mit Größenlimit und Content-Type-Prüfung;
- ZIP/TAR-Extraktion gegen Path Traversal absichern;
- Raw HTML/JSON nie als Code oder Template ausführen;
- Modellartefakte bevorzugt als `state_dict` plus Config, keine untrusted Pickles laden;
- externe Artefakte nur nach Checksum-/Manifestprüfung.
