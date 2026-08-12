"""Stable application failures safe for CLI rendering."""

from __future__ import annotations

import re

_CODE = re.compile(r"^[A-Z][A-Z0-9_]+$")


def exit_code_for_error(code: str) -> int:
    if code.startswith(("CONFIG_", "SECURITY_")):
        return 2
    if code.startswith("POLICY_"):
        return 3
    if code.startswith(("QUALITY_", "SPLIT_", "LEGAL_")):
        return 4
    if code.startswith(("INTEGRITY_", "RESOLVE_")):
        return 5
    if code.startswith(("ACQ_", "EXTERNAL_")):
        return 7
    return 10


class ApplicationError(RuntimeError):
    """Safe, namespaced failure without raw endpoint, secret, or payload text."""

    def __init__(self, code: str, *, exit_code: int | None = None) -> None:
        if _CODE.fullmatch(code) is None:
            raise ValueError("application error codes must be stable uppercase tokens")
        self.code = code
        self.exit_code = exit_code if exit_code is not None else exit_code_for_error(code)
        super().__init__(code)


def from_port_error(error: BaseException, fallback: str) -> ApplicationError:
    """Convert a port failure to a safe application error using only a stable code."""

    candidate = getattr(error, "code", None)
    code = candidate if isinstance(candidate, str) and _CODE.fullmatch(candidate) else fallback
    return ApplicationError(code)


__all__ = ["ApplicationError", "exit_code_for_error", "from_port_error"]
