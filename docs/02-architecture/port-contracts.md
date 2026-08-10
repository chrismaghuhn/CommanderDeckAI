# Port-Verträge

Die folgenden Signaturen sind Architekturvorgaben, keine zwingend identischen Python-Namen. Methoden bleiben klein, streamingfähig und frei von versteckter I/O.

```python
class CardCatalog(Protocol):
    def get_card(self, oracle_id: UUID, snapshot_id: str) -> Card: ...
    def get_ruleset(self, ruleset_version: str) -> RulesetSnapshot: ...
    def iter_legal_candidates(self, query: LegalCandidateQuery) -> Iterator[Card]: ...


class DeckRepository(Protocol):
    def get(self, deck_id: str) -> Deck: ...
    def iter(self, query: DeckQuery) -> Iterator[Deck]: ...


class SourceAdapter(Protocol):
    source_id: str

    def acquire(self, request: SnapshotRequest) -> SourceSnapshotManifest: ...
    def normalize(self, snapshot_id: str) -> NormalizedSnapshotManifest: ...


class DatasetRepository(Protocol):
    def load_manifest(self, dataset_id: str) -> DatasetManifest: ...
    def open_split(self, dataset_id: str, split: str) -> CompletionExampleStream: ...


class CardRanker(Protocol):
    model_id: str

    def score(self, request: RankContext, candidates: CandidateBatch) -> ScoreBatch: ...


class ScoreSnapshotRepository(Protocol):
    def put(self, snapshot: ScoreSnapshot) -> None: ...
    def get(self, score_snapshot_id: str) -> ScoreSnapshot: ...


class DeckOptimizer(Protocol):
    optimizer_profile_id: str

    def optimize(
        self, request: OptimizationRequest, scores: ScoreSnapshot
    ) -> OptimizationResult: ...


class ModelRegistry(Protocol):
    def load_ranker(self, model_id: str) -> CardRanker: ...
    def verify(self, model_id: str) -> ModelManifest: ...


class ForgeGateway(Protocol):
    def enqueue(self, request: ForgeEvaluationRequest) -> str: ...
    def collect(self, request_id: str) -> ForgeEvaluationResult | None: ...
```

## Regeln

- Iterator/Batch statt `list` für große Datenmengen;
- IDs und Snapshots explizit;
- keine Methode liest globales `latest`;
- `CardRanker` verändert keine Daten;
- `DeckOptimizer` erhält Scores per Vertrag, nicht per Callback;
- Repositories geben Domain-/Contracttypen, keine DuckDB-Cursor zurück.
