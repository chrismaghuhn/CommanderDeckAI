"""Bounded decoding of HTTP entity content codings after raw capture."""

from __future__ import annotations

import gzip
import io
import re
import zlib

DEFAULT_MAX_DECODED_BYTES = 2_000_000_000
_CODING_TOKEN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class HttpContentCodingError(ValueError):
    """Safe, stable error for unsupported or unsafe entity decoding."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def decode_entity_body(
    raw_bytes: bytes,
    content_encoding: str | None,
    *,
    max_decoded_bytes: int = DEFAULT_MAX_DECODED_BYTES,
) -> bytes:
    """Decode a raw HTTP entity only after it has been durably captured."""

    if not isinstance(raw_bytes, bytes):
        raise HttpContentCodingError("HTTP_ENTITY_INVALID")
    if (
        not isinstance(max_decoded_bytes, int)
        or isinstance(max_decoded_bytes, bool)
        or max_decoded_bytes < 1
    ):
        raise HttpContentCodingError("HTTP_DECODED_SIZE_LIMIT_INVALID")
    encodings = _parse_encodings(content_encoding)
    decoded = raw_bytes
    for encoding in reversed(encodings):
        if encoding == "identity":
            continue
        if encoding == "gzip":
            decoded = _decode_gzip(decoded, max_decoded_bytes)
        elif encoding == "deflate":
            decoded = _decode_deflate(decoded, max_decoded_bytes)
        else:
            raise HttpContentCodingError("HTTP_CONTENT_ENCODING_UNSUPPORTED")
    return decoded


def _parse_encodings(content_encoding: str | None) -> tuple[str, ...]:
    if content_encoding is None:
        return ()
    if not isinstance(content_encoding, str):
        raise HttpContentCodingError("HTTP_CONTENT_ENCODING_INVALID")
    if not content_encoding.strip():
        return ()
    values = tuple(item.strip().casefold() for item in content_encoding.split(","))
    if not values or any(not _CODING_TOKEN.fullmatch(item) for item in values):
        raise HttpContentCodingError("HTTP_CONTENT_ENCODING_INVALID")
    return values


def _decode_gzip(raw_bytes: bytes, max_decoded_bytes: int) -> bytes:
    output = bytearray()
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw_bytes), mode="rb") as stream:
            while chunk := stream.read(min(1024 * 1024, max_decoded_bytes + 1)):
                output.extend(chunk)
                if len(output) > max_decoded_bytes:
                    raise HttpContentCodingError("HTTP_DECOMPRESSED_SIZE_LIMIT")
    except HttpContentCodingError:
        raise
    except (OSError, EOFError, zlib.error):
        raise HttpContentCodingError("HTTP_CONTENT_ENCODING_INVALID") from None
    return bytes(output)


def _decode_deflate(raw_bytes: bytes, max_decoded_bytes: int) -> bytes:
    decompressor = zlib.decompressobj()
    output = bytearray()
    try:
        for offset in range(0, len(raw_bytes), 1024 * 1024):
            chunk = raw_bytes[offset : offset + 1024 * 1024]
            output.extend(decompressor.decompress(chunk, max_decoded_bytes + 1 - len(output)))
            if len(output) > max_decoded_bytes:
                raise HttpContentCodingError("HTTP_DECOMPRESSED_SIZE_LIMIT")
            if decompressor.unconsumed_tail:
                raise HttpContentCodingError("HTTP_DECOMPRESSED_SIZE_LIMIT")
        output.extend(decompressor.flush(max_decoded_bytes + 1 - len(output)))
    except HttpContentCodingError:
        raise
    except (zlib.error, ValueError):
        raise HttpContentCodingError("HTTP_CONTENT_ENCODING_INVALID") from None
    if len(output) > max_decoded_bytes:
        raise HttpContentCodingError("HTTP_DECOMPRESSED_SIZE_LIMIT")
    if not decompressor.eof:
        raise HttpContentCodingError("HTTP_CONTENT_ENCODING_INVALID")
    return bytes(output)


__all__ = [
    "DEFAULT_MAX_DECODED_BYTES",
    "HttpContentCodingError",
    "decode_entity_body",
]
