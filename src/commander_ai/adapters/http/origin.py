"""Origin comparison for redirect credential forwarding decisions."""

from __future__ import annotations

from urllib.parse import urlsplit


def same_origin(first_url: str, second_url: str) -> bool:
    """Return whether two URLs share scheme, host, and effective port."""

    try:
        first = urlsplit(first_url)
        second = urlsplit(second_url)
        first_port = first.port or (443 if first.scheme.casefold() == "https" else 80)
        second_port = second.port or (443 if second.scheme.casefold() == "https" else 80)
        return (
            first.scheme.casefold() == second.scheme.casefold()
            and first.hostname is not None
            and second.hostname is not None
            and first.hostname.casefold().rstrip(".") == second.hostname.casefold().rstrip(".")
            and first_port == second_port
        )
    except (TypeError, ValueError):
        return False


__all__ = ["same_origin"]
