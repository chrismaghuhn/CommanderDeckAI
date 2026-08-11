"""Bounded, link-free inspection and extraction for source archives."""

from __future__ import annotations

import os
import shutil
import stat
import struct
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import IO


class ArchiveSafetyError(RuntimeError):
    """Archive rejection with a stable security or resource-limit code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ArchiveLimits:
    max_compressed_bytes: int = 2_000_000_000
    max_uncompressed_bytes: int = 10_000_000_000
    max_file_bytes: int = 2_000_000_000
    max_compression_ratio: float = 200.0

    def __post_init__(self) -> None:
        if (
            self.max_compressed_bytes < 1
            or self.max_uncompressed_bytes < 1
            or self.max_file_bytes < 1
        ):
            raise ValueError("archive byte limits must be positive")
        if self.max_compression_ratio <= 0:
            raise ValueError("archive compression ratio must be positive")


@dataclass(frozen=True, slots=True)
class ArchiveMember:
    name: str
    is_dir: bool
    compressed_bytes: int
    uncompressed_bytes: int


@dataclass(frozen=True, slots=True)
class ArchiveInspection:
    members: tuple[ArchiveMember, ...]
    compressed_bytes: int
    uncompressed_bytes: int


@dataclass(frozen=True, slots=True)
class ArchiveExtraction:
    root: Path
    files: tuple[Path, ...]


def inspect_archive(path: Path | str, *, limits: ArchiveLimits | None = None) -> ArchiveInspection:
    """Inspect archive metadata and reject unsafe names, links, and bombs."""

    archive_path = _source_path(path)
    selected_limits = limits or ArchiveLimits()
    try:
        compressed_bytes = archive_path.stat().st_size
    except OSError as error:
        raise ArchiveSafetyError("SECURITY_ARCHIVE_SOURCE") from error
    if compressed_bytes > selected_limits.max_compressed_bytes:
        raise ArchiveSafetyError("SECURITY_ARCHIVE_COMPRESSED_LIMIT")
    try:
        if zipfile.is_zipfile(archive_path):
            return _inspect_zip(archive_path, compressed_bytes, selected_limits)
        return _inspect_tar(archive_path, compressed_bytes, selected_limits)
    except ArchiveSafetyError:
        raise
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        raise ArchiveSafetyError("SECURITY_ARCHIVE_FORMAT") from error


def extract_archive(
    path: Path | str,
    destination: Path | str,
    *,
    limits: ArchiveLimits | None = None,
    chunk_bytes: int = 1024 * 1024,
    runtime_limit: int | None = None,
) -> ArchiveExtraction:
    """Extract only validated regular members through a temporary root."""

    if chunk_bytes < 1:
        raise ValueError("chunk_bytes must be positive")
    archive_path = _source_path(path)
    destination_path = Path(destination).expanduser()
    if destination_path.exists() or destination_path.is_symlink():
        raise ArchiveSafetyError("SECURITY_EXTRACTION_DESTINATION_EXISTS")
    try:
        destination_parent = destination_path.parent.resolve()
        destination_parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ArchiveSafetyError("SECURITY_EXTRACTION_FAILED") from error
    inspection = inspect_archive(archive_path, limits=limits)
    selected_limits = limits or ArchiveLimits()
    temporary_root = Path(tempfile.mkdtemp(prefix=".extract-", dir=destination_parent))
    files: list[Path] = []
    total_written = 0
    try:
        if zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path) as archive:
                for zip_info in archive.infolist():
                    if zip_info.is_dir() or zip_info.filename.endswith("/"):
                        continue
                    member_name = _member_name(zip_info.filename)
                    target = _new_target(temporary_root, member_name)
                    with archive.open(zip_info, "r") as zip_stream:
                        written = _copy_member(
                            zip_stream,
                            target,
                            chunk_bytes,
                            selected_limits,
                            total_written,
                            runtime_limit,
                        )
                    total_written += written
                    files.append(destination_path / member_name)
        else:
            with tarfile.open(archive_path, mode="r:*") as archive:
                for tar_info in archive.getmembers():
                    if tar_info.isdir():
                        continue
                    tar_stream = archive.extractfile(tar_info)
                    if tar_stream is None:
                        raise ArchiveSafetyError("SECURITY_ARCHIVE_MEMBER")
                    member_name = _member_name(tar_info.name)
                    target = _new_target(temporary_root, member_name)
                    with tar_stream:
                        written = _copy_member(
                            tar_stream,
                            target,
                            chunk_bytes,
                            selected_limits,
                            total_written,
                            runtime_limit,
                        )
                    total_written += written
                    files.append(destination_path / member_name)
        if total_written != inspection.uncompressed_bytes:
            raise ArchiveSafetyError("SECURITY_ARCHIVE_UNCOMPRESSED_LIMIT")
        if destination_path.exists() or destination_path.is_symlink():
            raise ArchiveSafetyError("SECURITY_EXTRACTION_DESTINATION_EXISTS")
        os.replace(temporary_root, destination_path)
        return ArchiveExtraction(destination_path, tuple(files))
    except ArchiveSafetyError:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise ArchiveSafetyError("SECURITY_EXTRACTION_FAILED") from error


def _inspect_zip(path: Path, compressed_bytes: int, limits: ArchiveLimits) -> ArchiveInspection:
    members: list[ArchiveMember] = []
    names: set[str] = set()
    total_uncompressed = 0
    compressed_member_total = 0
    with zipfile.ZipFile(path) as archive:
        for raw_name in _raw_zip_names(path, archive.start_dir):
            _member_name(raw_name)
        for info in archive.infolist():
            name = _member_name(info.filename)
            if name in names:
                raise ArchiveSafetyError("SECURITY_ARCHIVE_DUPLICATE")
            names.add(name)
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise ArchiveSafetyError("SECURITY_ARCHIVE_LINK")
            is_dir = info.is_dir() or info.filename.endswith("/")
            compressed_size = max(0, info.compress_size)
            uncompressed_size = max(0, info.file_size)
            if not is_dir:
                _check_member_limits(
                    compressed_size,
                    uncompressed_size,
                    total_uncompressed,
                    limits,
                )
                total_uncompressed += uncompressed_size
                compressed_member_total += compressed_size
            members.append(ArchiveMember(name, is_dir, compressed_size, uncompressed_size))
    if total_uncompressed / max(compressed_bytes, 1) > limits.max_compression_ratio:
        raise ArchiveSafetyError("SECURITY_ARCHIVE_RATIO_LIMIT")
    if compressed_member_total > limits.max_compressed_bytes:
        raise ArchiveSafetyError("SECURITY_ARCHIVE_COMPRESSED_LIMIT")
    return ArchiveInspection(tuple(members), compressed_bytes, total_uncompressed)


def _inspect_tar(path: Path, compressed_bytes: int, limits: ArchiveLimits) -> ArchiveInspection:
    members: list[ArchiveMember] = []
    names: set[str] = set()
    total_uncompressed = 0
    with tarfile.open(path, mode="r:*") as archive:
        for info in archive.getmembers():
            name = _member_name(info.name)
            if name in names:
                raise ArchiveSafetyError("SECURITY_ARCHIVE_DUPLICATE")
            names.add(name)
            if info.issym() or info.islnk() or not (info.isdir() or info.isreg()):
                raise ArchiveSafetyError("SECURITY_ARCHIVE_LINK")
            uncompressed_size = max(0, info.size)
            if not info.isdir():
                _check_member_limits(0, uncompressed_size, total_uncompressed, limits)
                total_uncompressed += uncompressed_size
            members.append(ArchiveMember(name, info.isdir(), 0, uncompressed_size))
    if total_uncompressed / max(compressed_bytes, 1) > limits.max_compression_ratio:
        raise ArchiveSafetyError("SECURITY_ARCHIVE_RATIO_LIMIT")
    return ArchiveInspection(tuple(members), compressed_bytes, total_uncompressed)


def _raw_zip_names(path: Path, start: int) -> tuple[str, ...]:
    with path.open("rb") as stream:
        stream.seek(start)
        central_directory = stream.read()
    names: list[str] = []
    offset = 0
    fixed_size = 46
    while offset + fixed_size <= len(central_directory):
        if central_directory[offset : offset + 4] != b"PK\x01\x02":
            break
        fields = struct.unpack_from("<4s6H3L5H2L", central_directory, offset)
        filename_length = fields[10]
        extra_length = fields[11]
        comment_length = fields[12]
        begin = offset + fixed_size
        end = begin + filename_length
        if end + extra_length + comment_length > len(central_directory):
            raise ArchiveSafetyError("SECURITY_ARCHIVE_FORMAT")
        raw_name = central_directory[begin:end]
        try:
            name = raw_name.decode("utf-8" if fields[3] & 0x800 else "cp437")
        except UnicodeDecodeError as error:
            raise ArchiveSafetyError("SECURITY_ARCHIVE_PATH") from error
        names.append(name)
        offset = end + extra_length + comment_length
    if not names:
        raise ArchiveSafetyError("SECURITY_ARCHIVE_FORMAT")
    return tuple(names)


def _copy_member(
    stream: IO[bytes],
    target: Path,
    chunk_bytes: int,
    limits: ArchiveLimits,
    prior_total: int,
    runtime_limit: int | None,
) -> int:
    written = 0
    with target.open("xb") as output:
        while chunk := stream.read(chunk_bytes):
            if not isinstance(chunk, bytes):
                raise ArchiveSafetyError("SECURITY_ARCHIVE_MEMBER")
            written += len(chunk)
            if written > limits.max_file_bytes:
                raise ArchiveSafetyError("SECURITY_ARCHIVE_FILE_LIMIT")
            if prior_total + written > limits.max_uncompressed_bytes:
                raise ArchiveSafetyError("SECURITY_ARCHIVE_UNCOMPRESSED_LIMIT")
            if runtime_limit is not None and prior_total + written > runtime_limit:
                raise ArchiveSafetyError("SECURITY_ARCHIVE_UNCOMPRESSED_LIMIT")
            output.write(chunk)
        output.flush()
        os.fsync(output.fileno())
    return written


def _check_member_limits(
    compressed_size: int,
    uncompressed_size: int,
    prior_total: int,
    limits: ArchiveLimits,
) -> None:
    if uncompressed_size > limits.max_file_bytes:
        raise ArchiveSafetyError("SECURITY_ARCHIVE_FILE_LIMIT")
    if prior_total + uncompressed_size > limits.max_uncompressed_bytes:
        raise ArchiveSafetyError("SECURITY_ARCHIVE_UNCOMPRESSED_LIMIT")
    if compressed_size > 0 and uncompressed_size / compressed_size > limits.max_compression_ratio:
        raise ArchiveSafetyError("SECURITY_ARCHIVE_RATIO_LIMIT")


def _source_path(path: Path | str) -> Path:
    source = Path(path).expanduser()
    if not source.is_file() or source.is_symlink():
        raise ArchiveSafetyError("SECURITY_ARCHIVE_SOURCE")
    return source.resolve()


def _new_target(root: Path, name: str) -> Path:
    target = (root / PurePosixPath(name)).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as error:
        raise ArchiveSafetyError("SECURITY_ARCHIVE_PATH") from error
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _member_name(name: str) -> str:
    if not isinstance(name, str) or not name or "\x00" in name or "\\" in name:
        raise ArchiveSafetyError("SECURITY_ARCHIVE_PATH")
    if name.endswith("/"):
        name = name[:-1]
    if not name or name.startswith("/") or name.startswith("//"):
        raise ArchiveSafetyError("SECURITY_ARCHIVE_PATH")
    windows = PureWindowsPath(name)
    if windows.drive or windows.root or windows.anchor:
        raise ArchiveSafetyError("SECURITY_ARCHIVE_PATH")
    parts = PurePosixPath(name).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ArchiveSafetyError("SECURITY_ARCHIVE_PATH")
    if PurePosixPath(name).as_posix() != name:
        raise ArchiveSafetyError("SECURITY_ARCHIVE_PATH")
    return name


__all__ = [
    "ArchiveExtraction",
    "ArchiveInspection",
    "ArchiveLimits",
    "ArchiveMember",
    "ArchiveSafetyError",
    "extract_archive",
    "inspect_archive",
]
