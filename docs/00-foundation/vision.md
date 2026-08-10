# Vision

Commander Deck AI soll ein offenes, reproduzierbares System werden, das **Deckkonstruktion als Empfehlung und Optimierung** behandelt.

Das System beantwortet zuerst eine begrenzte, messbare Frage:

> Welche legalen Karten passen zu einem Commander und einem bereits vorhandenen Teildeck?

Danach beantwortet ein separater Optimizer:

> Welche Auswahl erfüllt alle harten Regeln und die expliziten Ziele des Nutzers am besten?

Langfristig kann Turnier- und Forge-Evidenz den Score verbessern. Menschliche Decklisten bleiben dabei ein Prior, nicht die alleinige Wahrheit.

## Qualitätsversprechen

- jede Empfehlung ist auf Score-Komponenten zurückführbar;
- jedes Deck durchläuft einen unabhängigen Legalitätsvalidator;
- jedes Modell ist gegen simple Baselines gemessen;
- jedes Dataset besitzt Provenienz, Snapshot und Leakage-Bericht;
- Casual und cEDH werden nicht unter einer einzigen Winrate-Zielfunktion vermischt.
