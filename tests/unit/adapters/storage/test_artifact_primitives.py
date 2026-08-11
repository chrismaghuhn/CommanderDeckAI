from __future__ import annotations

import copy
import hashlib
import io
from pathlib import Path

import pytest

from commander_ai.adapters.storage.canonical_json import canonical_json_bytes
from commander_ai.adapters.storage.digests import (
    DETACHED_MANIFEST_DIGEST_FIELD,
    detached_manifest_sha256,
    raw_object_sha256,
    snapshot_content_bytes,
    snapshot_content_sha256,
)
from commander_ai.adapters.storage.path_policy import (
    normalize_portable_relative_path,
    resolve_under_root,
    to_portable_relative_path,
    validate_portable_relative_path,
)


def test_canonical_json_emits_exact_utf8_bytes() -> None:
    value = {
        "z": "Grüße",
        "é": "雪",
        "items": ["zweite", "erste"],
        "a": "é",
    }

    assert canonical_json_bytes(value) == (
        b'{"a":"e\xcc\x81","items":["zweite","erste"],"z":"Gr\xc3\xbc\xc3\x9fe",'
        b'"\xc3\xa9":"\xe9\x9b\xaa"}'
    )


def test_canonical_json_preserves_list_order() -> None:
    assert canonical_json_bytes({"items": ["b", "a"]}) == b'{"items":["b","a"]}'
    assert canonical_json_bytes({"items": ["a", "b"]}) == b'{"items":["a","b"]}'


@pytest.mark.parametrize(
    ("value", "error_type"),
    [
        (object(), TypeError),
        ({"value": {1, 2}}, TypeError),
        ({1: "non-string key"}, TypeError),
        ({"value": b"raw"}, TypeError),
        ({"value": float("nan")}, ValueError),
        ({"value": float("inf")}, ValueError),
    ],
)
def test_canonical_json_rejects_unsupported_or_ambiguous_values(
    value: object, error_type: type[Exception]
) -> None:
    with pytest.raises(error_type):
        canonical_json_bytes(value)


def test_raw_object_sha256_hashes_exact_bytes_and_streams() -> None:
    first = b"raw-object"
    second = b"raw-object\n"

    assert raw_object_sha256(first) == hashlib.sha256(first).hexdigest()
    assert raw_object_sha256(bytearray(first)) == hashlib.sha256(first).hexdigest()
    assert raw_object_sha256(io.BytesIO(first)) == hashlib.sha256(first).hexdigest()
    assert raw_object_sha256(first) != raw_object_sha256(second)


def test_raw_object_sha256_rejects_text_streams() -> None:
    with pytest.raises(TypeError):
        raw_object_sha256(io.StringIO("raw-object"))


def test_snapshot_content_bytes_use_exact_sorted_object_hash_payload() -> None:
    objects = [
        {
            "raw_object_id": "ä",
            "bytes": 3,
            "sha256": "c" * 64,
            "request_id": "excluded-request-metadata",
        },
        {
            "raw_object_id": "z",
            "bytes": 2,
            "sha256": "b" * 64,
            "retrieved_at": object(),
        },
        {
            "raw_object_id": "a",
            "bytes": 1,
            "sha256": "a" * 64,
        },
    ]
    expected = (
        b'{"objects":[{"bytes":1,"raw_object_id":"a","sha256":"'
        + b"a" * 64
        + b'"},{"bytes":2,"raw_object_id":"z","sha256":"'
        + b"b" * 64
        + b'"},{"bytes":3,"raw_object_id":"\xc3\xa4","sha256":"'
        + b"c" * 64
        + b'"}]}'
    )

    assert snapshot_content_bytes(objects) == expected
    assert snapshot_content_sha256(objects) == hashlib.sha256(expected).hexdigest()


def test_snapshot_content_digest_ignores_input_order_and_request_metadata() -> None:
    first = [
        {"raw_object_id": "b", "bytes": 2, "sha256": "b" * 64, "request_id": "one"},
        {"raw_object_id": "a", "bytes": 1, "sha256": "a" * 64, "request_id": "two"},
    ]
    second = [
        {"raw_object_id": "a", "bytes": 1, "sha256": "a" * 64, "request_id": object()},
        {"raw_object_id": "b", "bytes": 2, "sha256": "b" * 64, "request_id": None},
    ]

    assert snapshot_content_sha256(first) == snapshot_content_sha256(second)


@pytest.mark.parametrize(
    "objects",
    [
        [
            {"raw_object_id": "duplicate", "bytes": 1, "sha256": "a" * 64},
            {"raw_object_id": "duplicate", "bytes": 2, "sha256": "b" * 64},
        ],
        [{"raw_object_id": "negative", "bytes": -1, "sha256": "a" * 64}],
        [{"raw_object_id": "float", "bytes": 1.0, "sha256": "a" * 64}],
        [{"raw_object_id": "boolean", "bytes": True, "sha256": "a" * 64}],
        [{"raw_object_id": "uppercase", "bytes": 1, "sha256": "A" * 64}],
        [{"raw_object_id": "short", "bytes": 1, "sha256": "a" * 63}],
        [{"raw_object_id": "invalid", "bytes": 1, "sha256": "g" * 64}],
        [{"raw_object_id": "", "bytes": 1, "sha256": "a" * 64}],
        [{"raw_object_id": 1, "bytes": 1, "sha256": "a" * 64}],
        [{"raw_object_id": "missing-hash", "bytes": 1}],
    ],
)
def test_snapshot_content_digest_rejects_invalid_object_metadata(
    objects: list[dict[str, object]],
) -> None:
    with pytest.raises(ValueError):
        snapshot_content_sha256(objects)


def test_detached_manifest_digest_omits_only_documented_field_without_mutation() -> None:
    manifest = {
        "schema_version": "source-snapshot-manifest.v2",
        "name": "Märchen",
        "sha256": "raw-or-snapshot-field",
        DETACHED_MANIFEST_DIGEST_FIELD: "0" * 64,
    }
    original = copy.deepcopy(manifest)
    expected_payload = (
        b'{"name":"M\xc3\xa4rchen","schema_version":"source-snapshot-manifest.v2",'
        b'"sha256":"raw-or-snapshot-field"}'
    )

    assert detached_manifest_sha256(manifest) == hashlib.sha256(expected_payload).hexdigest()
    assert manifest == original


def test_detached_manifest_digest_does_not_omit_unrelated_sha256_field() -> None:
    with_self_digest = {
        "sha256": "retained",
        DETACHED_MANIFEST_DIGEST_FIELD: "0" * 64,
    }
    without_self_digest = {"sha256": "retained"}

    assert detached_manifest_sha256(with_self_digest) == detached_manifest_sha256(
        without_self_digest
    )
    assert detached_manifest_sha256({"sha256": "changed"}) != detached_manifest_sha256(
        without_self_digest
    )


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/root/file",
        "//server/share",
        "C:/data/file",
        "C:\\data\\file",
        "\\\\server\\share",
        "objects\\file.bin",
        "objects/../file.bin",
        "objects/./file.bin",
        "objects//file.bin",
        "objects/\x00file.bin",
        "<external-root>",
        "<repository-root>",
        "objects/<repository-root>/file.bin",
        "~/machine-specific/file.bin",
    ],
)
def test_portable_path_policy_rejects_nonportable_paths(path: str) -> None:
    with pytest.raises(ValueError):
        validate_portable_relative_path(path)
    with pytest.raises(ValueError):
        normalize_portable_relative_path(path)


def test_portable_path_policy_returns_posix_root_relative_paths(tmp_path: Path) -> None:
    root = tmp_path / "artifact-root"
    target = root / "nested" / "artifact.json"
    target.parent.mkdir(parents=True)

    assert normalize_portable_relative_path("nested/artifact.json") == "nested/artifact.json"
    assert to_portable_relative_path(target, root) == "nested/artifact.json"
    assert to_portable_relative_path("nested/artifact.json", root) == "nested/artifact.json"
    assert resolve_under_root(root, "nested/artifact.json") == target.resolve()


def test_portable_path_policy_rejects_absolute_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "artifact-root"
    outside = tmp_path / "outside" / "artifact.json"

    with pytest.raises(ValueError):
        to_portable_relative_path(outside, root)


@pytest.mark.parametrize("marker", ["<external-root>", "<repository-root>"])
def test_portable_path_policy_rejects_non_reloadable_root_markers(marker: str) -> None:
    with pytest.raises(ValueError):
        resolve_under_root(marker, "artifact.json")


def test_portable_path_policy_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "artifact-root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")

    with pytest.raises(ValueError):
        resolve_under_root(root, "escape/artifact.json")
    with pytest.raises(ValueError):
        to_portable_relative_path(root / "escape" / "artifact.json", root)


def test_portable_path_policy_resolves_symlink_that_stays_inside_root(tmp_path: Path) -> None:
    root = tmp_path / "artifact-root"
    inside = root / "inside"
    root.mkdir()
    inside.mkdir()
    link = root / "link"
    try:
        link.symlink_to(inside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")

    assert resolve_under_root(root, "link/artifact.json") == (inside / "artifact.json").resolve()
