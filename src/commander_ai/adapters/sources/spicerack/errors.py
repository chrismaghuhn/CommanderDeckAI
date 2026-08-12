"""Stable, secret-free failures for the Spicerack adapter."""

from __future__ import annotations


class SpicerackError(RuntimeError):
    """Base error carrying only a stable machine-readable code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class SpicerackClientError(SpicerackError):
    """Request construction or response-policy failure."""


class SpicerackDownloadError(SpicerackError):
    """Raw acquisition failure."""


class SpicerackParseError(SpicerackError):
    """Failure to consume verified raw response evidence."""


class SpicerackStagingError(SpicerackError):
    """Failure to bind a source record to verified evidence."""


__all__ = [
    "SpicerackClientError",
    "SpicerackDownloadError",
    "SpicerackError",
    "SpicerackParseError",
    "SpicerackStagingError",
]
