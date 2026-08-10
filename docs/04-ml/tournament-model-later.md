# Tournament-/Pod-Modell — späterer Reranker

## Aufgabe

Schätze für cEDH-Kontext einen zusätzlichen Outcome-Score aus vier Deckrepräsentationen, Eventzeit, Sitz und Meta-Snapshot.

## Warum separat?

Turnierdaten sind kleiner, selektionsverzerrt und von Spielerkompetenz, Pairings, Sitzordnung, Concessions und Eventregeln beeinflusst. Diese Labels dürfen nicht das allgemeine Deck-Completion-Modell dominieren.

## Datensplit

- vollständig zeitbasiert;
- Event als unteilbare Gruppe;
- keine spätere Meta-Statistik als Feature;
- wiederkehrende Spieler-IDs nur pseudonym und primär für Bias-Audit, nicht als Produktfeature.

## Modellstart

Zuerst einfache regularisierte Modelle auf eingefrorenen Deckembeddings. Ein komplexes Multiplayer-Netz folgt nur bei ausreichender Datenmenge und stabiler Calibration.

## Ausgabe

Outcome-Score plus Unsicherheitsband und Datenabdeckung. Keine Behauptung, ein Deck sei objektiv „stärker“, wenn die Evidenz dünn ist.
