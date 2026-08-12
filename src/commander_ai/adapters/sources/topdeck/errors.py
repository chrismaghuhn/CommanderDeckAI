"""Stable, secret-free TopDeck adapter failures."""

from __future__ import annotations


class TopDeckError(RuntimeError):
    """Base error whose public value is a stable machine-readable code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class TopDeckClientError(TopDeckError):
    """Request-construction or transport boundary failure."""


class TopDeckDownloadError(TopDeckError):
    """Raw snapshot acquisition failure."""


class TopDeckParseError(TopDeckError):
    """Failure to read verified raw response evidence."""


class TopDeckStagingError(TopDeckError):
    """Failure to bind a staging record to verified source evidence."""


__all__ = [
    "TopDeckClientError",
    "TopDeckDownloadError",
    "TopDeckError",
    "TopDeckParseError",
    "TopDeckStagingError",
]
