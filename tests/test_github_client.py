from __future__ import annotations

import pytest

from codementor.github.client import (
    GitHubAuthError,
    GitHubClient,
    GitHubNotFoundError,
    GitHubRateLimitError,
)


def test_get_pull_request_sets_headers(httpx_mock) -> None:
    base_url = "https://api.github.test"
    httpx_mock.add_response(
        method="GET",
        url=f"{base_url}/repos/acme/demo/pulls/1",
        json={"number": 1},
    )

    client = GitHubClient(token="token", base_url=base_url)
    result = client.get_pull_request("acme", "demo", 1)

    assert result["number"] == 1
    request = httpx_mock.get_requests()[0]
    assert request.headers["Authorization"].startswith("Bearer ")
    assert request.headers["Accept"] == "application/vnd.github+json"


def test_get_pull_request_raises_not_found(httpx_mock) -> None:
    base_url = "https://api.github.test"
    httpx_mock.add_response(
        method="GET",
        url=f"{base_url}/repos/acme/demo/pulls/404",
        status_code=404,
    )

    client = GitHubClient(token="token", base_url=base_url)
    with pytest.raises(GitHubNotFoundError):
        client.get_pull_request("acme", "demo", 404)


def test_get_pull_request_raises_rate_limit(httpx_mock) -> None:
    base_url = "https://api.github.test"
    httpx_mock.add_response(
        method="GET",
        url=f"{base_url}/repos/acme/demo/pulls/2",
        status_code=403,
        headers={"X-RateLimit-Remaining": "0"},
    )

    client = GitHubClient(token="token", base_url=base_url)
    with pytest.raises(GitHubRateLimitError):
        client.get_pull_request("acme", "demo", 2)


def test_missing_token_raises_auth_error() -> None:
    client = GitHubClient(token=None, base_url="https://api.github.test")
    with pytest.raises(GitHubAuthError):
        client.get_workflow_runs("acme", "demo")
