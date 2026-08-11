"""Crash-safe same-filesystem file primitives for raw snapshot storage."""

from __future__ import annotations

import hashlib
import os
import tempfile
from contextlib import suppress
from pathlib import Path


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
            os.close(descriptor)
        with suppress(OSError):
            path.unlink()
        raise


def publish_new(temp_path: Path, final_path: Path) -> None:
    """Publish without replacing an existing immutable object."""

    os.link(temp_path, final_path)
    temp_path.unlink()


def fsync_directory(directory: Path) -> None:
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = ["fsync_directory", "publish_new", "sha256_file", "write_temp_file"]
