"""Spicerack public decklist source adapter."""

from .client import SpicerackClient, SpicerackRequest
from .downloader import SpicerackDownloader, SpicerackDownloadResult
from .dto import (
    SpicerackDecklistDTO,
    SpicerackEventDTO,
    SpicerackFinding,
    SpicerackParsedRecord,
    SpicerackPlayerDTO,
    SpicerackResultDTO,
    SpicerackStandingDTO,
)
from .errors import (
    SpicerackClientError,
    SpicerackDownloadError,
    SpicerackError,
    SpicerackParseError,
    SpicerackStagingError,
)
from .parser import SpicerackParser
from .settings import SpicerackSettings
from .staging import SpicerackStagingMapper

__all__ = [
    "SpicerackClient",
    "SpicerackClientError",
    "SpicerackDecklistDTO",
    "SpicerackDownloadError",
    "SpicerackDownloadResult",
    "SpicerackDownloader",
    "SpicerackError",
    "SpicerackEventDTO",
    "SpicerackFinding",
    "SpicerackParseError",
    "SpicerackParsedRecord",
    "SpicerackParser",
    "SpicerackPlayerDTO",
    "SpicerackRequest",
    "SpicerackResultDTO",
    "SpicerackSettings",
    "SpicerackStagingError",
    "SpicerackStagingMapper",
    "SpicerackStandingDTO",
]
