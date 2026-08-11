"""Documented TopDeck Tournaments v2 client over shared HTTP infrastructure."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from dataclasses import dataclass

import httpx
from pydantic import ValidationError

from commander_ai.adapters.http.redaction import sanitize_endpoint
from commander_ai.adapters.http.redirect_policy import RedirectPolicy, RedirectPolicyError
from commander_ai.adapters.http.transport import HttpTransport, HttpTransportError, SafeHttpResponse
from commander_ai.application.source_policy import SourcePolicy, SourcePolicyError
from commander_ai.config.current_use_policy import PolicyOperation
from commander_ai.domain.serialization import canonical_json_bytes

from .errors import TopDeckClientError
from .settings import TopDeckSettings


@dataclass(frozen=True, slots=True)
class TopDeckRequest:
    """One canonical query body and its provenance digest."""

    parameters: Mapping[str, object]
    body: bytes
    body_sha256: str


class TopDeckClient:
    """Build gated authenticated requests without retaining credential values."""

    def __init__(
        self,
        settings: TopDeckSettings,
        *,
        policy: SourcePolicy,
        http_client: httpx.Client | None = None,
    ) -> None:
        try:
            validated = TopDeckSettings.model_validate(settings.model_dump())
        except (AttributeError, TypeError, ValueError, ValidationError):
            raise TopDeckClientError("TOPDECK_SETTINGS_INVALID") from None
        self._settings = validated
        self._source_policy = policy
        self._redirect_policy = RedirectPolicy(validated.source.host_allowlist, max_redirects=0)
        self._transport = HttpTransport(
            allowed_hosts=set(validated.source.host_allowlist),
            timeout_seconds=validated.source.timeout_seconds,
            max_retries=validated.source.max_retries,
            max_response_bytes=validated.max_response_bytes,
            max_redirects=0,
            respect_retry_after=validated.source.respect_retry_after,
            rate_limit_per_minute=validated.source.rate_limit_per_minute,
            client=http_client,
        )

    @property
    def settings(self) -> TopDeckSettings:
        return self._settings

    def matches_settings(self, settings: TopDeckSettings) -> bool:
        try:
            candidate = TopDeckSettings.model_validate(settings.model_dump())
        except (AttributeError, TypeError, ValueError, ValidationError):
            return False
        return self._settings == candidate and self._redirect_policy.allowed_hosts == frozenset(
            candidate.source.host_allowlist
        )

    def build_request(self, parameters: Mapping[str, object]) -> TopDeckRequest:
        """Serialize one configured request body exactly once."""

        expected = self._settings.request_parameter_sets()
        if not any(
            canonical_json_bytes(parameters) == canonical_json_bytes(item) for item in expected
        ):
            raise TopDeckClientError("TOPDECK_REQUEST_INVALID")
        body = canonical_json_bytes(parameters)
        if len(body) > min(self._settings.max_response_bytes, 1_000_000):
            raise TopDeckClientError("TOPDECK_REQUEST_TOO_LARGE")
        return TopDeckRequest(
            parameters=dict(parameters),
            body=body,
            body_sha256=hashlib.sha256(body).hexdigest(),
        )

    def request_metadata(self, request: TopDeckRequest) -> dict[str, object]:
        """Return safe request provenance, including the exact body digest."""

        try:
            metadata = self._transport.request_metadata(
                "POST",
                self._settings.endpoint,
                parameters=request.parameters,
                api_version=self._settings.api_version,
                format="json",
            )
        except HttpTransportError as error:
            raise TopDeckClientError(error.code) from None
        if metadata.get("sanitized_endpoint") != sanitize_endpoint(self._settings.endpoint):
            raise TopDeckClientError("TOPDECK_METADATA_ENDPOINT_MISMATCH")
        metadata["request_body_sha256"] = request.body_sha256
        return metadata

    def fetch_tournaments(self, request: TopDeckRequest) -> SafeHttpResponse:
        """Check the current source gate before reading credentials or sending bytes."""

        try:
            self._source_policy.require_operation(
                self._settings.source.source_id,
                PolicyOperation.SOURCE_SYNC,
            )
        except SourcePolicyError as error:
            raise TopDeckClientError(error.code) from None
        api_key = os.environ.get(self._settings.api_key_env)
        if not isinstance(api_key, str) or not api_key.strip():
            raise TopDeckClientError("TOPDECK_CREDENTIAL_MISSING")
        try:
            self._redirect_policy.validate(self._settings.endpoint)
            response = self._transport.request(
                "POST",
                self._settings.endpoint,
                headers={
                    "Authorization": api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                request_body=request.body,
                api_version=self._settings.api_version,
                format="json",
            )
        except (RedirectPolicyError, TypeError):
            raise TopDeckClientError("TOPDECK_ENDPOINT_NOT_ALLOWLISTED") from None
        except HttpTransportError as error:
            if error.code == "SECURITY_RESPONSE_HOST":
                raise TopDeckClientError("TOPDECK_RESPONSE_HOST_NOT_ALLOWLISTED") from None
            raise TopDeckClientError(error.code) from None
        try:
            self._redirect_policy.validate(response.sanitized_endpoint)
        except (RedirectPolicyError, TypeError):
            response.close()
            raise TopDeckClientError("TOPDECK_RESPONSE_HOST_NOT_ALLOWLISTED") from None
        if response.sanitized_endpoint != sanitize_endpoint(self._settings.endpoint):
            response.close()
            raise TopDeckClientError("TOPDECK_RESPONSE_ENDPOINT_MISMATCH")
        return response

    def close(self) -> None:
        self._transport.close()


__all__ = ["TopDeckClient", "TopDeckRequest"]
