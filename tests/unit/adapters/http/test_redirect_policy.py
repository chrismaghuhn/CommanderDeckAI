from __future__ import annotations

import pytest

from commander_ai.adapters.http.redirect_policy import RedirectPolicy, RedirectPolicyError


def test_redirect_policy_allows_only_explicit_hosts_for_each_hop() -> None:
    policy = RedirectPolicy({"allowed.example", "cdn.allowed.example"}, max_redirects=2)

    first = policy.resolve("https://allowed.example/start", "/next", redirects_followed=0)
    second = policy.resolve(first, "https://cdn.allowed.example/final", redirects_followed=1)

    assert first == "https://allowed.example/next"
    assert second == "https://cdn.allowed.example/final"

    with pytest.raises(RedirectPolicyError) as error:
        policy.resolve(second, "https://evil.example/steal", redirects_followed=2)
    assert error.value.code == "SECURITY_REDIRECT_HOST"


@pytest.mark.parametrize(
    "location",
    [
        "file:///tmp/secret",
        "https://user:password@allowed.example/private",
        "\\\\server\\share\\private",
        "https://allowed.example/../private",
        "https://allowed.example/unsafe\x00path",
    ],
)
def test_redirect_policy_rejects_unsafe_destinations(location: str) -> None:
    policy = RedirectPolicy({"allowed.example"})

    with pytest.raises(RedirectPolicyError) as error:
        policy.resolve("https://allowed.example/start", location, redirects_followed=0)
    assert error.value.code.startswith("SECURITY_REDIRECT_")


def test_initial_endpoint_rejects_backslash_syntax() -> None:
    policy = RedirectPolicy({"allowed.example"})

    with pytest.raises(RedirectPolicyError) as error:
        policy.validate("https://allowed.example\\private")
    assert error.value.code == "SECURITY_ENDPOINT_URL"


def test_redirect_policy_has_a_bounded_chain() -> None:
    policy = RedirectPolicy({"allowed.example"}, max_redirects=1)

    policy.resolve("https://allowed.example/start", "/one", redirects_followed=0)
    with pytest.raises(RedirectPolicyError) as error:
        policy.resolve("https://allowed.example/one", "/two", redirects_followed=1)
    assert error.value.code == "HTTP_REDIRECT_LIMIT"
