from __future__ import annotations

import logging

from codementor.ci.parse_mypy import parse_mypy_output
from codementor.ci.parse_pytest import parse_pytest_output
from codementor.ci.parse_ruff import parse_ruff_output
from codementor.config import AppConfig
from codementor.github.actions import get_latest_workflow_run, get_run_artifacts
from codementor.github.artifacts import download_artifact_payload, extract_artifact_files
from codementor.github.client import GitHubClient, GitHubClientError
from codementor.mock_loader import load_json, MOCKS_DIR


logger = logging.getLogger(__name__)

EXPECTED_FILES = ("ruff.json", "mypy.txt", "pytest.json")


def _normalize_findings(findings: list) -> list[dict]:
    return [item.model_dump() for item in findings]


def _parse_artifacts(raw_files: dict[str, bytes]) -> dict[str, list[dict]]:
    ruff_raw = raw_files.get("ruff.json")
    mypy_raw = raw_files.get("mypy.txt")
    pytest_raw = raw_files.get("pytest.json")

    ruff_findings = parse_ruff_output(ruff_raw.decode("utf-8", errors="ignore")) if ruff_raw else []
    mypy_findings = parse_mypy_output(mypy_raw.decode("utf-8", errors="ignore")) if mypy_raw else []
    pytest_findings = parse_pytest_output(pytest_raw.decode("utf-8", errors="ignore")) if pytest_raw else []

    return {
        "ruff": _normalize_findings(ruff_findings),
        "mypy": _normalize_findings(mypy_findings),
        "pytest": _normalize_findings(pytest_findings),
    }


def get_ci_results(
    mode: str,
    owner: str | None = None,
    repo: str | None = None,
    pr_number: int | None = None,
    head_sha: str | None = None,
    client: GitHubClient | None = None,
    config: AppConfig | None = None,
) -> dict[str, list[dict]]:
    if mode == "mock":
        payload = load_json(MOCKS_DIR / "mock_ci_errors.json")
        if isinstance(payload, dict):
            return payload
        raise ValueError("Mock CI payload must be a dictionary.")

    if not (owner and repo and client and config):
        raise ValueError("GitHub mode requires owner, repo, client, and config.")

    run = get_latest_workflow_run(
        client,
        owner,
        repo,
        head_sha=head_sha,
        pr_number=pr_number,
        workflow_name=config.workflow_name,
    )
    if not run:
        raise GitHubClientError("No matching workflow run found for the PR.")

    artifacts = get_run_artifacts(client, owner, repo, run.get("id"))
    artifact = next(
        (item for item in artifacts if item.get("name") == config.artifact_name),
        None,
    )
    if not artifact:
        raise GitHubClientError(
            f"Artifact '{config.artifact_name}' not found in workflow run."
        )

    artifact_id = artifact.get("id")
    if not isinstance(artifact_id, int):
        raise GitHubClientError("Artifact payload missing an id.")

    zip_bytes = download_artifact_payload(client, owner, repo, artifact_id)
    raw_files = extract_artifact_files(zip_bytes, EXPECTED_FILES)
    if not raw_files:
        logger.warning("No expected CI files found in artifact payload.")
    return _parse_artifacts(raw_files)
