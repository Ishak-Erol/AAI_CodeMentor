from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

import httpx


logger = logging.getLogger(__name__)


class GitHubClientError(RuntimeError):
    """Base error for GitHub API issues."""


class GitHubAuthError(GitHubClientError):
    """Raised when authentication fails."""


class GitHubRateLimitError(GitHubClientError):
    """Raised when GitHub rate limit is exceeded."""


class GitHubNotFoundError(GitHubClientError):
    """Raised when a resource does not exist."""


@dataclass(frozen=True)
class GitHubRequest:
    method: str
    path: str


class GitHubClient:
    def __init__(
        self,
        token: str | None,
        base_url: str,
        timeout: float = 15.0,
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        if not self._token:
            raise GitHubAuthError("GITHUB_TOKEN is required for GitHub API access.")
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _request(
        self,
        request: GitHubRequest,
        params: dict[str, Any] | None = None,
        expect_json: bool = True,
    ) -> Any:
        url = f"{self._base_url}{request.path}"
        logger.info("GitHub API request %s %s", request.method, url)
        try:
            with httpx.Client(
                headers=self._headers(),
                timeout=self._timeout,
                follow_redirects=True,
            ) as client:
                response = client.request(
                    request.method,
                    url,
                    params=params,
                )
        except httpx.HTTPError as exc:
            raise GitHubClientError("Network error while calling GitHub API.") from exc

        if response.status_code >= 400:
            self._raise_for_status(response)

        if not expect_json:
            return response.content

        try:
            return response.json()
        except ValueError as exc:
            raise GitHubClientError("GitHub API returned invalid JSON.") from exc

    def _raise_for_status(self, response: httpx.Response) -> None:
        status = response.status_code
        if status == 404:
            raise GitHubNotFoundError("GitHub resource not found.")
        if status == 401:
            raise GitHubAuthError("GitHub API authentication failed.")
        if status == 403:
            remaining = response.headers.get("X-RateLimit-Remaining")
            if remaining == "0":
                raise GitHubRateLimitError("GitHub API rate limit exceeded.")
            raise GitHubAuthError("GitHub API access forbidden.")
        raise GitHubClientError(f"GitHub API request failed with status {status}.")

    def get_pull_request(self, owner: str, repo: str, pr_number: int) -> dict:
        return self._request(
            GitHubRequest("GET", f"/repos/{owner}/{repo}/pulls/{pr_number}")
        )

    def get_pull_request_files(self, owner: str, repo: str, pr_number: int) -> list[dict]:
        items: list[dict] = []
        page = 1
        while True:
            data = self._request(
                GitHubRequest(
                    "GET",
                    f"/repos/{owner}/{repo}/pulls/{pr_number}/files",
                ),
                params={"per_page": 100, "page": page},
            )
            if not isinstance(data, list):
                raise GitHubClientError("GitHub API returned unexpected files payload.")
            items.extend(data)
            if len(data) < 100:
                break
            page += 1
        return items

    def get_pull_request_reviews(self, owner: str, repo: str, pr_number: int) -> list[dict]:
        return self._request(
            GitHubRequest(
                "GET",
                f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            ),
            params={"per_page": 100},
        )

    def get_review_comments(self, owner: str, repo: str, pr_number: int) -> list[dict]:
        return self._request(
            GitHubRequest(
                "GET",
                f"/repos/{owner}/{repo}/pulls/{pr_number}/comments",
            ),
            params={"per_page": 100},
        )

    def get_workflow_runs(self, owner: str, repo: str) -> list[dict]:
        payload = self._request(
            GitHubRequest("GET", f"/repos/{owner}/{repo}/actions/runs"),
            params={"per_page": 100},
        )
        if not isinstance(payload, dict):
            raise GitHubClientError("GitHub API returned unexpected workflow payload.")
        return payload.get("workflow_runs", [])

    def get_workflow_run_artifacts(self, owner: str, repo: str, run_id: int) -> list[dict]:
        payload = self._request(
            GitHubRequest(
                "GET",
                f"/repos/{owner}/{repo}/actions/runs/{run_id}/artifacts",
            ),
            params={"per_page": 100},
        )
        if not isinstance(payload, dict):
            raise GitHubClientError("GitHub API returned unexpected artifact payload.")
        return payload.get("artifacts", [])

    def get_artifact(self, owner: str, repo: str, artifact_id: int) -> bytes:
        return self._request(
            GitHubRequest(
                "GET",
                f"/repos/{owner}/{repo}/actions/artifacts/{artifact_id}/zip",
            ),
            expect_json=False,
        )
