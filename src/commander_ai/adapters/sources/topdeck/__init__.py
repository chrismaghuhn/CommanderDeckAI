"""TopDeck.gg Tournaments v2 source adapter."""

from .client import TopDeckClient
from .downloader import TopDeckDownloader, TopDeckDownloadResult
from .dto import (
    TopDeckDeckDTO,
    TopDeckEventDTO,
    TopDeckFinding,
    TopDeckParsedRecord,
    TopDeckPlayerDTO,
    TopDeckRoundDTO,
    TopDeckStandingDTO,
    TopDeckTableDTO,
)
from .parser import TopDeckParser
from .settings import TopDeckSettings
from .staging import TopDeckStagingMapper

__all__ = [
    "TopDeckClient",
    "TopDeckDeckDTO",
    "TopDeckDownloadResult",
    "TopDeckDownloader",
    "TopDeckEventDTO",
    "TopDeckFinding",
    "TopDeckParsedRecord",
    "TopDeckParser",
    "TopDeckPlayerDTO",
    "TopDeckRoundDTO",
    "TopDeckSettings",
    "TopDeckStagingMapper",
    "TopDeckStandingDTO",
    "TopDeckTableDTO",
]
