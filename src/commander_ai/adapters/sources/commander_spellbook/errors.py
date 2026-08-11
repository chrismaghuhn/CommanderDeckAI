"""Stable, secret-free errors for the Commander Spellbook adapter."""

from __future__ import annotations


class CommanderSpellbookError(RuntimeError):
    """Base error carrying only a safe, stable failure code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class CommanderSpellbookConfigurationError(CommanderSpellbookError):
    """Settings or client binding failed closed."""


class CommanderSpellbookClientError(CommanderSpellbookError):
    """Request construction or source response policy failed."""


class CommanderSpellbookDownloadError(CommanderSpellbookError):
    """Raw acquisition could not reach a complete snapshot."""


__all__ = [
    "CommanderSpellbookClientError",
    "CommanderSpellbookConfigurationError",
    "CommanderSpellbookDownloadError",
    "CommanderSpellbookError",
]
