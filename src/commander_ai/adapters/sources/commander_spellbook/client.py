"""Documented Commander Spellbook reads over shared bounded HTTP transport."""

from __future__ import annotations

import httpx
from pydantic import ValidationError

from commander_ai.adapters.http.redaction import sanitize_endpoint
from commander_ai.adapters.http.redirect_policy import RedirectPolicy, RedirectPolicyError
from commander_ai.adapters.http.transport import HttpTransport, HttpTransportError, SafeHttpResponse

from .errors import CommanderSpellbookClientError
from .settings import CommanderSpellbookSettings, SpellbookContract


class CommanderSpellbookClient:
    """Construct only configured cards/variants GET requests."""

    def __init__(
        self,
        settings: CommanderSpellbookSettings,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        try:
            validated_settings = CommanderSpellbookSettings.model_validate(settings.model_dump())
        except (AttributeError, TypeError, ValueError, ValidationError):
            raise CommanderSpellbookClientError("SPELLBOOK_SETTINGS_INVALID") from None
        self._settings = validated_settings
        self._policy = RedirectPolicy(validated_settings.source.host_allowlist)
        self._transport = HttpTransport(
            allowed_hosts=set(validated_settings.source.host_allowlist),
            timeout_seconds=validated_settings.source.timeout_seconds,
            max_retries=validated_settings.source.max_retries,
            max_response_bytes=validated_settings.max_response_bytes,
            respect_retry_after=validated_settings.source.respect_retry_after,
            rate_limit_per_minute=validated_settings.source.rate_limit_per_minute,
            client=http_client,
        )

    @property
    def settings(self) -> CommanderSpellbookSettings:
        return self._settings

    def matches_settings(self, settings: CommanderSpellbookSettings) -> bool:
        try:
            CommanderSpellbookSettings.model_validate(self._settings.model_dump())
            CommanderSpellbookSettings.model_validate(settings.model_dump())
        except (TypeError, ValueError, ValidationError):
            return False
        return self._settings == settings and self._policy.allowed_hosts == frozenset(
            settings.source.host_allowlist
        )

    def request_metadata(
        self, contract: SpellbookContract | str, *, page: int
    ) -> dict[str, object]:
        self._validate_page(page)
        url = self._url(contract)
        metadata = self._transport.request_metadata(
            "GET",
            url,
            parameters={"page": page},
            format="json",
        )
        if metadata.get("sanitized_endpoint") != sanitize_endpoint(url):
            raise CommanderSpellbookClientError("SPELLBOOK_METADATA_ENDPOINT_MISMATCH")
        return metadata

    def fetch(self, contract: SpellbookContract | str, *, page: int) -> SafeHttpResponse:
        self._validate_page(page)
        url = self._url(contract)
        try:
            response = self._transport.request(
                "GET",
                url,
                parameters={"page": page},
                format="json",
            )
        except HttpTransportError as error:
            if error.code == "SECURITY_RESPONSE_HOST":
                raise CommanderSpellbookClientError(
                    "SPELLBOOK_RESPONSE_HOST_NOT_ALLOWLISTED"
                ) from None
            raise
        try:
            self._policy.validate(response.sanitized_endpoint)
        except (RedirectPolicyError, TypeError):
            response.close()
            raise CommanderSpellbookClientError("SPELLBOOK_RESPONSE_HOST_NOT_ALLOWLISTED") from None
        if response.sanitized_endpoint != sanitize_endpoint(url):
            response.close()
            raise CommanderSpellbookClientError("SPELLBOOK_RESPONSE_ENDPOINT_MISMATCH")
        return response

    def close(self) -> None:
        self._transport.close()

    def _url(self, contract: SpellbookContract | str) -> str:
        try:
            url = self._settings.endpoint(contract)
            self._policy.validate(url)
        except (RedirectPolicyError, TypeError, ValueError):
            raise CommanderSpellbookClientError("SPELLBOOK_ENDPOINT_NOT_ALLOWLISTED") from None
        return url

    def _validate_page(self, page: int) -> None:
        if (
            not isinstance(page, int)
            or isinstance(page, bool)
            or page < 1
            or page > self._settings.max_pages
        ):
            raise CommanderSpellbookClientError("SPELLBOOK_PAGE_INVALID")


__all__ = ["CommanderSpellbookClient", "CommanderSpellbookClientError"]
