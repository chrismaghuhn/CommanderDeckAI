"""Safe conversion of JSON-like mappings to HTTP query parameters."""

from __future__ import annotations

from collections.abc import Mapping

HttpQueryValue = str | int | float | bool | None | list[str | int | float | bool | None]


class QueryParameterError(ValueError):
    """A query value is outside the transport's bounded scalar contract."""


def query_parameters(
    parameters: Mapping[str, object] | None,
) -> dict[str, HttpQueryValue] | None:
    if parameters is None:
        return None
    result: dict[str, HttpQueryValue] = {}
    for key, value in parameters.items():
        if value is None or isinstance(value, (str, int, float, bool)):
            result[str(key)] = value
            continue
        if isinstance(value, (list, tuple)):
            values: list[str | int | float | bool | None] = []
            for item in value:
                if not (item is None or isinstance(item, (str, int, float, bool))):
                    raise QueryParameterError
                values.append(item)
            result[str(key)] = values
            continue
        raise QueryParameterError
    return result


__all__ = ["HttpQueryValue", "QueryParameterError", "query_parameters"]
