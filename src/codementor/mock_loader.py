from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from codementor.state import ReviewState, create_initial_state


ROOT = Path(__file__).resolve().parents[2]
MOCKS_DIR = ROOT / "mocks"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_mock_review_state(mocks_dir: Path | None = None) -> ReviewState:
    base = mocks_dir or MOCKS_DIR
    pr_data = load_json(base / "mock_pr.json")
    ci_findings = load_json(base / "mock_ci_errors.json")
    copilot_payload = load_json(base / "mock_copilot_review.json")
    copilot_comments = (
        copilot_payload["comments"]
        if isinstance(copilot_payload, dict) and "comments" in copilot_payload
        else copilot_payload
    )
    return create_initial_state(
        pr_data=pr_data,
        ci_findings=ci_findings,
        copilot_comments=copilot_comments,
    )
