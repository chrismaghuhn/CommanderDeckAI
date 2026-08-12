"""Bounded access to one regular member of an inspected source archive."""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path
from typing import IO

from .archive_safety import ArchiveLimits, ArchiveSafetyError, inspect_archive


def read_archive_member(
    path: Path | str,
    member_name: str,
    *,
    limits: ArchiveLimits | None = None,
    chunk_bytes: int = 1024 * 1024,
) -> bytes:
    """Inspect an archive, then read one regular member within shared limits."""

    if not isinstance(chunk_bytes, int) or isinstance(chunk_bytes, bool) or chunk_bytes < 1:
        raise ValueError("chunk_bytes must be positive")
    selected_limits = limits or ArchiveLimits()
    inspection = inspect_archive(path, limits=selected_limits)
    member = next(
        (item for item in inspection.members if item.name == member_name and not item.is_dir),
        None,
    )
    if member is None:
        raise ArchiveSafetyError("SECURITY_ARCHIVE_MEMBER_MISSING")

    archive_path = Path(path).expanduser()
    try:
        if zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path) as archive, archive.open(member_name, "r") as stream:
                return _read_bounded(stream, selected_limits, chunk_bytes)
        with tarfile.open(archive_path, mode="r:*") as tar_archive:
            tar_member = tar_archive.getmember(member_name)
            tar_stream = tar_archive.extractfile(tar_member)
            if tar_stream is None:
                raise ArchiveSafetyError("SECURITY_ARCHIVE_MEMBER_MISSING")
            with tar_stream:
                return _read_bounded(tar_stream, selected_limits, chunk_bytes)
    except ArchiveSafetyError:
        raise
    except (KeyError, OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        raise ArchiveSafetyError("SECURITY_ARCHIVE_MEMBER") from error


def _read_bounded(stream: IO[bytes], limits: ArchiveLimits, chunk_bytes: int) -> bytes:
    result = bytearray()
    while chunk := stream.read(chunk_bytes):
        if not isinstance(chunk, bytes):
            raise ArchiveSafetyError("SECURITY_ARCHIVE_MEMBER")
        result.extend(chunk)
        if len(result) > limits.max_file_bytes:
            raise ArchiveSafetyError("SECURITY_ARCHIVE_FILE_LIMIT")
        if len(result) > limits.max_uncompressed_bytes:
            raise ArchiveSafetyError("SECURITY_ARCHIVE_UNCOMPRESSED_LIMIT")
    return bytes(result)


__all__ = ["read_archive_member"]
