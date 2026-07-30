"""Gemeinsame Test-Fixtures.

Die JSON-Dateien in `fixtures/` sind aufgezeichnete GitHub-Payloads eines
Beispiel-Pull-Requests. Sie liefern den Tests einen realistischen
`ReviewState`, ohne dass ein GitHub-Token oder ein Netzwerkzugriff nötig ist.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from codementor.state import ReviewState, create_initial_state

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_review_state(fixtures_dir: Path | None = None) -> ReviewState:
    """Baut einen ReviewState aus den aufgezeichneten Beispiel-Payloads."""
    base = fixtures_dir or FIXTURES_DIR
    copilot_payload = load_json(base / "copilot_review.json")
    copilot_comments = (
        copilot_payload["comments"]
        if isinstance(copilot_payload, dict) and "comments" in copilot_payload
        else copilot_payload
    )
    return create_initial_state(
        pr_data=load_json(base / "pr.json"),
        ci_findings=load_json(base / "ci_errors.json"),
        copilot_comments=copilot_comments,
    )


@pytest.fixture
def review_state() -> ReviewState:
    """Beispiel-ReviewState mit pytest-, ruff- und Copilot-Befunden."""
    return build_review_state()
