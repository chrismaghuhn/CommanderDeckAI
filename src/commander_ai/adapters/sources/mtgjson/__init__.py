"""Approved, source-specific MTGJSON acquisition and staging adapter."""

from .client import MTGJSONClient, MTGJSONClientError
from .downloader import MTGJSONDownloader, MTGJSONDownloadError, MTGJSONDownloadResult
from .dto import (
    MTGJSONCard,
    MTGJSONCardFace,
    MTGJSONDeckProduct,
    MTGJSONFile,
    MTGJSONSet,
)
from .parser import (
    MTGJSONFinding,
    MTGJSONParsedRecord,
    MTGJSONParseError,
    MTGJSONParser,
    MTGJSONParseResult,
)
from .settings import MTGJSONProduct, MTGJSONSettings
from .staging import MTGJSONStagingMapper, map_to_staging

__all__ = [
    "MTGJSONCard",
    "MTGJSONCardFace",
    "MTGJSONClient",
    "MTGJSONClientError",
    "MTGJSONDeckProduct",
    "MTGJSONDownloadError",
    "MTGJSONDownloadResult",
    "MTGJSONDownloader",
    "MTGJSONFile",
    "MTGJSONFinding",
    "MTGJSONParseError",
    "MTGJSONParseResult",
    "MTGJSONParsedRecord",
    "MTGJSONParser",
    "MTGJSONProduct",
    "MTGJSONSet",
    "MTGJSONSettings",
    "MTGJSONStagingMapper",
    "map_to_staging",
]
