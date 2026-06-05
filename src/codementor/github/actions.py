from __future__ import annotations

from typing import Any

from codementor.github.client import GitHubClient


def select_workflow_run(
    runs: list[dict[str, Any]],
    head_sha: str | None,
    pr_number: int | None,
    workflow_name: str | None,
) -> dict[str, Any] | None:
    for run in runs:
        if workflow_name:
            if run.get("name") != workflow_name and run.get("workflow_name") != workflow_name:
                continue
        if head_sha and run.get("head_sha") != head_sha:
            continue
        if pr_number is not None:
            pull_requests = run.get("pull_requests", []) or []
            if not any(item.get("number") == pr_number for item in pull_requests):
                continue
        return run
    return None


def get_latest_workflow_run(
    client: GitHubClient,
    owner: str,
    repo: str,
    head_sha: str | None = None,
    pr_number: int | None = None,
    workflow_name: str | None = None,
) -> dict[str, Any] | None:
    runs = client.get_workflow_runs(owner, repo)
    return select_workflow_run(runs, head_sha, pr_number, workflow_name)


def get_run_artifacts(
    client: GitHubClient,
    owner: str,
    repo: str,
    run_id: int,
) -> list[dict[str, Any]]:
    return client.get_workflow_run_artifacts(owner, repo, run_id)
