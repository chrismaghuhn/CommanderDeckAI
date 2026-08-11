"""Namespaced finding codes for every non-curated pipeline outcome."""

from __future__ import annotations

import re
from typing import Literal

FindingNamespace = Literal["parse", "integrity", "resolution", "legality", "quality"]
FINDING_NAMESPACES = frozenset({"parse", "integrity", "resolution", "legality", "quality"})
_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")


class FindingCode(str):
    """Validated string value whose first segment identifies the pipeline stage."""

    def __new__(cls, value: str) -> FindingCode:
        if not isinstance(value, str) or _CODE_PATTERN.fullmatch(value) is None:
            raise ValueError("finding code must be namespaced with dot-separated segments")
        namespace = value.split(".", maxsplit=1)[0]
        if namespace not in FINDING_NAMESPACES:
            raise ValueError(f"unsupported finding namespace: {namespace}")
        return str.__new__(cls, value)

    @classmethod
    def parse(cls, value: str | FindingCode) -> FindingCode:
        return value if isinstance(value, cls) else cls(value)

    @property
    def namespace(self) -> FindingNamespace:
        return self.split(".", maxsplit=1)[0]  # type: ignore[return-value]


def validate_finding_code(value: str | FindingCode, *, namespace: str | None = None) -> str:
    code = FindingCode.parse(value)
    if namespace is not None and code.namespace != namespace:
        raise ValueError(f"finding code namespace must be {namespace}")
    return str(code)


def validate_finding_codes(
    values: tuple[str, ...] | list[str] | tuple[FindingCode, ...],
    *,
    namespace: str | None = None,
) -> tuple[str, ...]:
    return tuple(validate_finding_code(value, namespace=namespace) for value in values)


__all__ = [
    "FINDING_NAMESPACES",
    "FindingCode",
    "FindingNamespace",
    "validate_finding_code",
    "validate_finding_codes",
]
