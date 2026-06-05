from __future__ import annotations

from codementor.github.copilot import extract_copilot_comments


def test_extracts_only_copilot_reviews_and_comments() -> None:
    allowlist = ["copilot", "github-copilot[bot]"]
    reviews = [
        {"user": {"login": "copilot"}, "body": "General suggestion"},
        {"user": {"login": "human"}, "body": "LGTM"},
    ]
    comments = [
        {
            "user": {"login": "github-copilot[bot]"},
            "path": "src/app.py",
            "line": 12,
            "body": "Consider optional handling",
        },
        {
            "user": {"login": "reviewer"},
            "path": "src/app.py",
            "line": 15,
            "body": "Nitpick",
        },
    ]

    results = extract_copilot_comments(reviews, comments, allowlist)

    assert len(results) == 2
    assert results[0]["file"] == "general"
    assert results[1]["file"] == "src/app.py"


def test_extracts_no_comments_when_allowlist_missing() -> None:
    reviews = [{"user": {"login": "copilot"}, "body": "Hi"}]
    comments = []

    results = extract_copilot_comments(reviews, comments, ["other"])

    assert results == []
