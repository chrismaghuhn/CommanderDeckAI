"""Crash-safe same-filesystem file primitives for raw snapshot storage."""

from __future__ import annotations

import errno
import hashlib
import os
import tempfile
from contextlib import suppress
from pathlib import Path

_UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS = frozenset(
    value
    for value in (
        getattr(errno, "EINVAL", None),
        getattr(errno, "ENOSYS", None),
        getattr(errno, "ENOTSUP", None),
        getattr(errno, "EOPNOTSUPP", None),
        getattr(errno, "ENOTTY", None),
    )
    if value is not None
)


def write_temp_file(directory: Path, prefix: str, data: bytes) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=prefix, dir=directory)
    path = Path(name)
    try:
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("temporary file write made no progress")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        return path
    except OSError:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)
        with suppress(OSError):
            path.unlink()
        raise


def publish_new(temp_path: Path, final_path: Path) -> None:
    """Publish without replacing an existing immutable object."""

    os.link(temp_path, final_path)
    temp_path.unlink()


def fsync_directory(directory: Path) -> None:
    """Flush a directory or use the documented atomic fallback when unsupported.

    Windows does not expose a portable directory descriptor for ``fsync``. The
    caller has already fsynced every file, and ``link``/``replace`` provide the
    atomic publication boundary there. On other platforms only errors explicitly
    identifying an unsupported directory operation use that fallback; all other
    durability errors propagate and fail the snapshot.
    """

    if os.name == "nt":
        return
    try:
        descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError as error:
        if error.errno in _UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS:
            return
        raise
    try:
        try:
            os.fsync(descriptor)
        except OSError as error:
            if error.errno in _UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS:
                return
            raise
    finally:
        os.close(descriptor)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = ["fsync_directory", "publish_new", "sha256_file", "write_temp_file"]
