"""Typed row contracts allowed in the curated Parquet layer."""

from __future__ import annotations

from pydantic import BaseModel

from commander_ai.domain.cards import CanonicalCard, CardFace, Printing
from commander_ai.domain.dataset_row_contracts import TASK_DATASET_ROW_CONTRACTS


def curated_row_contracts(generic_row: type[BaseModel]) -> tuple[type[BaseModel], ...]:
    """Return the generic, task-specific, and card contracts for curated rows."""

    return (
        generic_row,
        *TASK_DATASET_ROW_CONTRACTS,
        CanonicalCard,
        CardFace,
        Printing,
    )


__all__ = ["curated_row_contracts"]
