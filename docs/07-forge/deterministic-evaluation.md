# Deterministische Forge-Evaluation

## Vergleichsdesign

- gleiche Agentversionen;
- explizite Seeds;
- Sitzrotationen über alle Decks;
- identische Mulligan-/Timeout-Policies;
- mehrere Replikate pro Konfiguration;
- Cache-Key über Decks, Versionen, Seats, Seeds und Parameter.

## Interpretation

Eine Winrate gegen einen schwachen oder verzerrten Agenten ist keine absolute Deckstärke. Forge-Evidenz ist zunächst **relative Vergleichsevidenz unter fixierter Simulator-/Agentkonfiguration**.

## Fehlerbehandlung

Abgebrochene, desynchronisierte oder regelinkompatible Games werden nicht als Loss gewertet. Sie erhalten eigene Statuscodes und fließen separat in Qualitätsberichte ein.
