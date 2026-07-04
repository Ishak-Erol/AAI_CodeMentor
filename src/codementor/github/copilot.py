from __future__ import annotations

from typing import Any


def _is_copilot_author(user: dict[str, Any] | None, allowlist: list[str]) -> bool:
    if not user:
        return False
    login = str(user.get("login", "")).lower()
    return login in allowlist


def extract_copilot_comments(
    reviews: list[dict[str, Any]],
    review_comments: list[dict[str, Any]],
    allowlist: list[str],
) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    for review in reviews:
        if not _is_copilot_author(review.get("user"), allowlist):
            continue
        body = str(review.get("body") or "").strip()
        if not body:
            continue
        comments.append(
            {
                "file": "general",
                "line": None,
                "comment": body,
                "author": review.get("user", {}).get("login"),
            }
        )

    for comment in review_comments:
        if not _is_copilot_author(comment.get("user"), allowlist):
            continue
        body = str(comment.get("body") or "").strip()
        if not body:
            continue
        comments.append(
            {
                "file": comment.get("path") or "unknown",
                "line": comment.get("line") or comment.get("original_line"),
                "comment": body,
                "author": comment.get("user", {}).get("login"),
            }
        )
    return comments


def extract_review_comments(
    reviews: list[dict[str, Any]],
    review_comments: list[dict[str, Any]],
    allowlist: list[str],
) -> list[dict[str, Any]]:
    """Like `extract_copilot_comments`, but keeps comments from every reviewer
    (human and Copilot), tagging each with its `source` instead of dropping
    non-allowlisted authors."""
    comments: list[dict[str, Any]] = []
    for review in reviews:
        body = str(review.get("body") or "").strip()
        if not body:
            continue
        user = review.get("user")
        comments.append(
            {
                "file": "general",
                "line": None,
                "comment": body,
                "author": (user or {}).get("login"),
                "source": "copilot" if _is_copilot_author(user, allowlist) else "human",
            }
        )

    for comment in review_comments:
        body = str(comment.get("body") or "").strip()
        if not body:
            continue
        user = comment.get("user")
        comments.append(
            {
                "file": comment.get("path") or "unknown",
                "line": comment.get("line") or comment.get("original_line"),
                "comment": body,
                "author": (user or {}).get("login"),
                "source": "copilot" if _is_copilot_author(user, allowlist) else "human",
            }
        )
    return comments
