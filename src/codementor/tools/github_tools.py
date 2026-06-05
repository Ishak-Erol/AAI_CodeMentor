from __future__ import annotations

from typing import Any

from codementor.config import AppConfig
from codementor.github.client import GitHubClient
from codementor.mock_loader import load_json, MOCKS_DIR


def _mock_review_comments() -> list[dict[str, Any]]:
    payload = load_json(MOCKS_DIR / "mock_copilot_review.json")
    if isinstance(payload, dict) and "comments" in payload:
        return payload["comments"]
    if isinstance(payload, list):
        return payload
    return []


def get_pr_data(
    mode: str,
    owner: str | None = None,
    repo: str | None = None,
    pr_number: int | None = None,
    client: GitHubClient | None = None,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    if mode == "mock":
        pr_data = load_json(MOCKS_DIR / "mock_pr.json")
        return {
            "pr_data": pr_data,
            "reviews": [],
            "review_comments": _mock_review_comments(),
        }

    if not (owner and repo and pr_number and client):
        raise ValueError("GitHub mode requires owner, repo, pr number, and client.")

    pr = client.get_pull_request(owner, repo, pr_number)
    files = client.get_pull_request_files(owner, repo, pr_number)
    reviews = client.get_pull_request_reviews(owner, repo, pr_number)
    review_comments = client.get_review_comments(owner, repo, pr_number)

    metadata = {
        "id": pr.get("number"),
        "title": pr.get("title"),
        "description": pr.get("body") or "",
        "author": pr.get("user", {}).get("login"),
        "source_branch": pr.get("head", {}).get("ref"),
        "target_branch": pr.get("base", {}).get("ref"),
        "url": pr.get("html_url"),
        "head_sha": pr.get("head", {}).get("sha"),
    }

    changed_files = []
    for item in files:
        changed_files.append(
            {
                "path": item.get("filename"),
                "status": item.get("status"),
                "diff": item.get("patch") or "",
            }
        )

    pr_data = {
        "metadata": metadata,
        "learning_context": {},
        "changed_files": changed_files,
    }

    return {
        "pr_data": pr_data,
        "reviews": reviews,
        "review_comments": review_comments,
    }
