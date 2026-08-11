"""Documented Spicerack read client over the shared bounded HTTP transport."""

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

from .errors import SpicerackClientError
from .settings import SpicerackSettings


@dataclass(frozen=True, slots=True)
class SpicerackRequest:
    parameters: Mapping[str, object]
    endpoint: str
    body_sha256: str


class SpicerackClient:
    """Construct gated, credential-safe requests for the configured read path."""

    def __init__(
        self,
        settings: SpicerackSettings,
        *,
        policy: SourcePolicy,
        http_client: httpx.Client | None = None,
    ) -> None:
        try:
            validated = SpicerackSettings.model_validate(settings.model_dump())
        except (AttributeError, TypeError, ValueError, ValidationError):
            raise SpicerackClientError("SPICERACK_SETTINGS_INVALID") from None
        self._settings = validated
        self._policy = policy
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
    def settings(self) -> SpicerackSettings:
        return self._settings

    def matches_settings(self, settings: SpicerackSettings) -> bool:
        try:
            candidate = SpicerackSettings.model_validate(settings.model_dump())
        except (AttributeError, TypeError, ValueError, ValidationError):
            return False
        return self._settings == candidate

    def build_request(
        self,
        parameters: Mapping[str, object],
        *,
        path: str | None = None,
    ) -> SpicerackRequest:
        selected_path = (
            self._settings.api_path if path is None else path if path.endswith("/") else f"{path}/"
        )
        if selected_path != self._settings.api_path:
            raise SpicerackClientError("SPICERACK_PATH_NOT_CONFIGURED")
        selected_format = (
            parameters.get("event_format") if isinstance(parameters, Mapping) else None
        )
        if not isinstance(selected_format, str) or selected_format not in self._settings.formats:
            raise SpicerackClientError("SPICERACK_REQUEST_INVALID")
        try:
            expected = self._settings.request_parameters(selected_format=selected_format)
        except ValueError:
            raise SpicerackClientError("SPICERACK_REQUEST_INVALID") from None
        if dict(parameters) != expected:
            raise SpicerackClientError("SPICERACK_REQUEST_INVALID")
        encoded = canonical_json_bytes(parameters)
        if len(encoded) > min(self._settings.max_response_bytes, 1_000_000):
            raise SpicerackClientError("SPICERACK_REQUEST_TOO_LARGE")
        return SpicerackRequest(
            parameters=dict(parameters),
            endpoint=f"{self._settings.source.endpoints[0].rstrip('/')}{selected_path}",
            body_sha256=hashlib.sha256(encoded).hexdigest(),
        )

    def request_metadata(self, request: SpicerackRequest) -> dict[str, object]:
        try:
            metadata = self._transport.request_metadata(
                "GET",
                request.endpoint,
                parameters=request.parameters,
                api_version="public-decklist-api",
                format=self._settings.response_format,
            )
        except HttpTransportError as error:
            raise SpicerackClientError(error.code) from None
        if metadata.get("sanitized_endpoint") != sanitize_endpoint(request.endpoint):
            raise SpicerackClientError("SPICERACK_METADATA_ENDPOINT_MISMATCH")
        return metadata

    def fetch_page(self, request: SpicerackRequest) -> SafeHttpResponse:
        """Apply current source policy before reading the credential or sending a request."""

        if not isinstance(request, SpicerackRequest):
            raise SpicerackClientError("SPICERACK_REQUEST_INVALID")
        try:
            configuration = self._policy.adapter_configuration(self._settings.source.source_id)
        except SourcePolicyError:
            raise
        if configuration.source != self._settings.source:
            raise SpicerackClientError("SPICERACK_POLICY_CONFIGURATION_MISMATCH")
        try:
            expected = self.build_request(request.parameters, path=self._settings.api_path)
        except SpicerackClientError:
            raise SpicerackClientError("SPICERACK_REQUEST_CONFIGURATION_MISMATCH") from None
        if request != expected:
            raise SpicerackClientError("SPICERACK_REQUEST_CONFIGURATION_MISMATCH")
        try:
            self._policy.require_operation(
                self._settings.source.source_id,
                PolicyOperation.SOURCE_SYNC,
            )
        except SourcePolicyError:
            raise
        api_key = os.environ.get(self._settings.api_key_env)
        if not isinstance(api_key, str) or not api_key.strip():
            raise SpicerackClientError("SPICERACK_CREDENTIAL_MISSING")
        try:
            self._redirect_policy.validate(request.endpoint)
            response = self._transport.request(
                "GET",
                request.endpoint,
                parameters=request.parameters,
                headers={
                    self._settings.credential_header: api_key,
                    "Accept": "application/json"
                    if self._settings.response_format == "json"
                    else "application/x-ndjson",
                },
                format=self._settings.response_format,
            )
        except (RedirectPolicyError, TypeError):
            raise SpicerackClientError("SPICERACK_ENDPOINT_NOT_ALLOWLISTED") from None
        except HttpTransportError as error:
            if error.code == "SECURITY_RESPONSE_HOST":
                raise SpicerackClientError("SPICERACK_RESPONSE_HOST_NOT_ALLOWLISTED") from None
            raise SpicerackClientError(error.code) from None
        try:
            self._redirect_policy.validate(response.sanitized_endpoint)
        except (RedirectPolicyError, TypeError):
            response.close()
            raise SpicerackClientError("SPICERACK_RESPONSE_HOST_NOT_ALLOWLISTED") from None
        if response.sanitized_endpoint != sanitize_endpoint(request.endpoint):
            response.close()
            raise SpicerackClientError("SPICERACK_RESPONSE_ENDPOINT_MISMATCH")
        return response

    def close(self) -> None:
        self._transport.close()


__all__ = ["SpicerackClient", "SpicerackClientError", "SpicerackRequest"]
