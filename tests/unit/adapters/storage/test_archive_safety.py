from __future__ import annotations

import io
import stat
import tarfile
import zipfile
from pathlib import Path

import pytest

from commander_ai.adapters.storage.archive_safety import (
    ArchiveLimits,
    ArchiveSafetyError,
    extract_archive,
    inspect_archive,
)


def _zip(path: Path, members: list[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in members:
            archive.writestr(name, content)


def test_zip_inspection_and_atomic_extraction_preserve_derived_member_bytes(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "all-printings.zip"
    _zip(archive_path, [("nested/cards.json", b'{"cards":[]}'), ("README.txt", b"derived")])
    destination = tmp_path / "views"

    inspection = inspect_archive(archive_path)
    result = extract_archive(archive_path, destination, destination_root=tmp_path)

    assert [member.name for member in inspection.members] == ["nested/cards.json", "README.txt"]
    assert result.root == destination
    assert (destination / "nested/cards.json").read_bytes() == b'{"cards":[]}'
    assert (destination / "README.txt").read_bytes() == b"derived"
    assert not list(tmp_path.glob(".extract-*"))


def test_tar_extraction_stays_atomic_and_preserves_member_bytes(tmp_path: Path) -> None:
    archive_path = tmp_path / "all-printings.tar"
    with tarfile.open(archive_path, "w") as archive:
        info = tarfile.TarInfo("nested/cards.json")
        content = b'{"cards":[]}'
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    destination = tmp_path / "views"

    inspection = inspect_archive(archive_path)
    result = extract_archive(archive_path, destination, destination_root=tmp_path)

    assert inspection.uncompressed_bytes == len(content)
    assert result.files == (destination / "nested/cards.json",)
    assert (destination / "nested/cards.json").read_bytes() == content


@pytest.mark.parametrize(
    "member_name",
    [
        "/absolute.json",
        "../outside.json",
        "nested/../../outside.json",
        "nested\\outside.json",
        "C:/outside.json",
        "\\\\server\\share\\outside.json",
        "nested/./file.json",
        "safe.txt:secret",
        "CON",
        "con.txt",
        "nested/COM1.log",
        "trailing-space. ",
    ],
)
def test_archive_member_path_escapes_are_rejected(tmp_path: Path, member_name: str) -> None:
    archive_path = tmp_path / "unsafe.zip"
    _zip(archive_path, [(member_name, b"unsafe")])
    if "\\" in member_name:
        normalized = member_name.replace("\\", "/").encode("utf-8")
        archive_bytes = archive_path.read_bytes()
        assert normalized in archive_bytes
        archive_path.write_bytes(archive_bytes.replace(normalized, member_name.encode("utf-8")))

    with pytest.raises(ArchiveSafetyError) as error:
        inspect_archive(archive_path)
    assert error.value.code == "SECURITY_ARCHIVE_PATH"


def test_zip_symlink_is_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo("link")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(info, "outside")

    with pytest.raises(ArchiveSafetyError) as error:
        inspect_archive(archive_path)
    assert error.value.code == "SECURITY_ARCHIVE_LINK"


def test_tar_hardlink_is_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "hardlink.tar"
    with tarfile.open(archive_path, "w") as archive:
        info = tarfile.TarInfo("hardlink")
        info.type = tarfile.LNKTYPE
        info.linkname = "outside"
        archive.addfile(info)

    with pytest.raises(ArchiveSafetyError) as error:
        inspect_archive(archive_path)
    assert error.value.code == "SECURITY_ARCHIVE_LINK"


@pytest.mark.parametrize(
    ("limits", "expected_code"),
    [
        (ArchiveLimits(max_compressed_bytes=1), "SECURITY_ARCHIVE_COMPRESSED_LIMIT"),
        (ArchiveLimits(max_uncompressed_bytes=3), "SECURITY_ARCHIVE_UNCOMPRESSED_LIMIT"),
        (ArchiveLimits(max_file_bytes=3), "SECURITY_ARCHIVE_FILE_LIMIT"),
        (ArchiveLimits(max_compression_ratio=2.0), "SECURITY_ARCHIVE_RATIO_LIMIT"),
    ],
)
def test_archive_limits_are_checked_before_extraction(
    tmp_path: Path, limits: ArchiveLimits, expected_code: str
) -> None:
    archive_path = tmp_path / "limited.zip"
    _zip(archive_path, [("cards.json", b"a" * 1_000)])

    with pytest.raises(ArchiveSafetyError) as error:
        inspect_archive(archive_path, limits=limits)
    assert error.value.code == expected_code


def test_limit_violation_during_extraction_leaves_no_partial_destination(tmp_path: Path) -> None:
    archive_path = tmp_path / "runtime-limit.zip"
    _zip(archive_path, [("cards.json", b"a" * 128)])
    destination = tmp_path / "views"
    limits = ArchiveLimits(max_uncompressed_bytes=1_000, max_file_bytes=1_000)

    with pytest.raises(ArchiveSafetyError):
        extract_archive(
            archive_path,
            destination,
            destination_root=tmp_path,
            limits=limits,
            chunk_bytes=8,
            runtime_limit=64,
        )

    assert not destination.exists()
    assert not list(tmp_path.glob(".extract-*"))


def test_existing_extraction_destination_is_never_overwritten(tmp_path: Path) -> None:
    archive_path = tmp_path / "archive.zip"
    _zip(archive_path, [("cards.json", b"new")])
    destination = tmp_path / "views"
    destination.mkdir()
    (destination / "old.txt").write_bytes(b"old")

    with pytest.raises(ArchiveSafetyError) as error:
        extract_archive(archive_path, destination, destination_root=tmp_path)
    assert error.value.code == "SECURITY_EXTRACTION_DESTINATION_EXISTS"
    assert (destination / "old.txt").read_bytes() == b"old"


def test_extraction_destination_must_be_below_configured_root(tmp_path: Path) -> None:
    archive_path = tmp_path / "archive.zip"
    _zip(archive_path, [("cards.json", b"derived")])
    allowed_root = tmp_path / "allowed"
    outside = tmp_path / "outside"

    with pytest.raises(ArchiveSafetyError) as error:
        extract_archive(archive_path, outside, destination_root=allowed_root)

    assert error.value.code == "SECURITY_EXTRACTION_ROOT"
    assert not outside.exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_compressed_bytes", float("inf")),
        ("max_uncompressed_bytes", float("nan")),
        ("max_file_bytes", float("inf")),
        ("max_compression_ratio", float("inf")),
        ("max_compression_ratio", float("nan")),
    ],
)
def test_archive_limits_reject_non_finite_values(field: str, value: float) -> None:
    with pytest.raises(ValueError):
        ArchiveLimits(**{field: value})
