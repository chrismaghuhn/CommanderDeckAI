"""Source-agnostic domain contracts and immutable value objects."""

from .cards import CardFace, CardIdentity, CardResolution, CardResolutionCandidate, Printing
from .combos import Combo, ComboCard
from .decks import (
    CanonicalDeck,
    CardQuantity,
    CardZone,
    CommandZoneEntry,
    CommandZoneRelationship,
    compute_structural_fingerprint,
)
from .evaluations import DeckLegalityEvaluation, DeckQualityEvaluation
from .observations import EventDeckObservation, ParticipantReference, PodEntry
from .provenance import (
    DatasetExclusion,
    DatasetInputReference,
    DatasetManifest,
    DatasetOutputReference,
    NormalizedSnapshotManifest,
    ProvenanceReference,
    QuarantineReference,
    RawObjectReference,
    RequestParametersSummary,
    SourceSnapshotManifest,
    SourceSnapshotRequest,
    derive_request_parameters_summary,
)

__all__ = [
    "CanonicalDeck",
    "CardFace",
    "CardIdentity",
    "CardQuantity",
    "CardResolution",
    "CardResolutionCandidate",
    "CardZone",
    "Combo",
    "ComboCard",
    "CommandZoneEntry",
    "CommandZoneRelationship",
    "DatasetExclusion",
    "DatasetInputReference",
    "DatasetManifest",
    "DatasetOutputReference",
    "DeckLegalityEvaluation",
    "DeckQualityEvaluation",
    "EventDeckObservation",
    "NormalizedSnapshotManifest",
    "ParticipantReference",
    "PodEntry",
    "Printing",
    "ProvenanceReference",
    "QuarantineReference",
    "RawObjectReference",
    "RequestParametersSummary",
    "SourceSnapshotManifest",
    "SourceSnapshotRequest",
    "compute_structural_fingerprint",
    "derive_request_parameters_summary",
]
