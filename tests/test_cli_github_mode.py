from __future__ import annotations

import json
import sys

import main


def test_cli_github_mode_requires_args(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setattr(sys, "argv", ["main.py", "--mode", "github"])

    exit_code = main.main()

    assert exit_code == 2


def test_cli_github_mode_runs_with_mocked_data(monkeypatch, capsys) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "token")

    def fake_pr_data(**_kwargs):
        return {
            "pr_data": {
                "metadata": {
                    "id": 1,
                    "title": "Title",
                    "description": "Body",
                    "author": "dev",
                    "source_branch": "feature",
                    "target_branch": "main",
                    "head_sha": "abc",
                },
                "learning_context": {},
                "changed_files": [
                    {"path": "src/app.py", "status": "modified", "diff": ""}
                ],
            },
            "reviews": [],
            "review_comments": [],
        }

    monkeypatch.setattr(main, "get_pr_data", fake_pr_data)
    monkeypatch.setattr(
        main,
        "get_ci_results",
        lambda **_kwargs: {"ruff": [], "mypy": [], "pytest": []},
    )
    monkeypatch.setattr(main, "extract_copilot_comments", lambda *_: [])
    monkeypatch.setattr(sys, "argv", [
        "main.py",
        "--mode",
        "github",
        "--owner",
        "acme",
        "--repo",
        "demo",
        "--pr",
        "1",
    ])

    exit_code = main.main()

    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "FINAL_STATE_JSON" in captured
    payload = captured.split("FINAL_STATE_JSON:\n", maxsplit=1)[1]
    data = json.loads(payload)
    assert data["mentor_feedback"]
