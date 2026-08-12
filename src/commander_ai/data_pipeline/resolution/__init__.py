"""Card catalog construction and deterministic identity resolution."""

from .canonical_cards import CardMappingError, canonical_card_from_staging, card_face_from_staging
from .card_catalog import AliasCatalog, CardCatalog, CardCatalogBuilder, CatalogBuildResult
from .card_resolution import (
    CardResolutionInput,
    CardResolver,
    ResolutionResult,
)

__all__ = [
    "AliasCatalog",
    "CardCatalog",
    "CardCatalogBuilder",
    "CardMappingError",
    "CardResolutionInput",
    "CardResolver",
    "CatalogBuildResult",
    "ResolutionResult",
    "canonical_card_from_staging",
    "card_face_from_staging",
]
