from __future__ import annotations

import io
import zipfile
from typing import Iterable

from codementor.github.client import GitHubClient, GitHubClientError


def extract_artifact_files(
    archive_bytes: bytes,
    expected_names: Iterable[str],
) -> dict[str, bytes]:
    results: dict[str, bytes] = {}
    expected = {name.lower() for name in expected_names}
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as handle:
        for name in handle.namelist():
            lowered = name.lower()
            base = lowered.rsplit("/", maxsplit=1)[-1]
            if base in expected:
                results[base] = handle.read(name)
    return results


def download_artifact_payload(
    client: GitHubClient,
    owner: str,
    repo: str,
    artifact_id: int,
) -> bytes:
    payload = client.get_artifact(owner, repo, artifact_id)
    if not payload:
        raise GitHubClientError("Artifact download returned empty payload.")
    return payload
