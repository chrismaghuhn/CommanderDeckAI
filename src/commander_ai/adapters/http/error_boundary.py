"""Detach raw exception context at public HTTP transport boundaries."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from functools import wraps
from typing import ParamSpec, TypeVar

_Parameters = ParamSpec("_Parameters")
_Return = TypeVar("_Return")
_Item = TypeVar("_Item")


def detach_exception_chain(error: BaseException) -> None:
    """Remove raw exception references from a sanitized public error."""

    error.__cause__ = None
    error.__context__ = None
    error.__suppress_context__ = True


def detached_error_boundary(
    exception_type: type[BaseException],
) -> Callable[[Callable[_Parameters, _Return]], Callable[_Parameters, _Return]]:
    """Decorate a regular function with a sanitized exception boundary."""

    def decorate(
        function: Callable[_Parameters, _Return],
    ) -> Callable[_Parameters, _Return]:
        @wraps(function)
        def wrapped(*args: _Parameters.args, **kwargs: _Parameters.kwargs) -> _Return:
            try:
                return function(*args, **kwargs)
            except exception_type as error:
                detach_exception_chain(error)
                raise

        return wrapped

    return decorate


def detached_generator_boundary(
    exception_type: type[BaseException],
) -> Callable[[Callable[_Parameters, Iterator[_Item]]], Callable[_Parameters, Iterator[_Item]]]:
    """Decorate a streaming generator with a sanitized exception boundary."""

    def decorate(
        function: Callable[_Parameters, Iterator[_Item]],
    ) -> Callable[_Parameters, Iterator[_Item]]:
        @wraps(function)
        def wrapped(*args: _Parameters.args, **kwargs: _Parameters.kwargs) -> Iterator[_Item]:
            try:
                yield from function(*args, **kwargs)
            except exception_type as error:
                detach_exception_chain(error)
                raise

        return wrapped

    return decorate


__all__ = [
    "detach_exception_chain",
    "detached_error_boundary",
    "detached_generator_boundary",
]
