from __future__ import annotations

import gzip
import zlib

import pytest

from commander_ai.adapters.http.content_coding import (
    HttpContentCodingError,
    decode_entity_body,
)


@pytest.mark.parametrize(
    ("encoded", "content_encoding"),
    (
        (gzip.compress(b'{"results":[]}'), "gzip"),
        (zlib.compress(b'{"results":[]}'), "deflate"),
    ),
)
def test_entity_decoder_handles_supported_content_codings(
    encoded: bytes, content_encoding: str
) -> None:
    assert decode_entity_body(encoded, content_encoding) == b'{"results":[]}'


def test_entity_decoder_applies_codings_after_raw_capture() -> None:
    payload = b'{"results":[]}'
    encoded = gzip.compress(zlib.compress(payload))

    assert decode_entity_body(encoded, "deflate, gzip") == payload


def test_entity_decoder_rejects_unsupported_coding_and_decompression_bombs() -> None:
    with pytest.raises(HttpContentCodingError) as unsupported:
        decode_entity_body(b"raw", "br")
    assert unsupported.value.code == "HTTP_CONTENT_ENCODING_UNSUPPORTED"

    with pytest.raises(HttpContentCodingError) as oversized:
        decode_entity_body(gzip.compress(b"0123456789"), "gzip", max_decoded_bytes=5)
    assert oversized.value.code == "HTTP_DECOMPRESSED_SIZE_LIMIT"
