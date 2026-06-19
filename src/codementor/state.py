from __future__ import annotations

from typing import Any, TypedDict


class ReviewState(TypedDict):
    pr_data: dict[str, Any]
    ci_findings: dict[str, Any]
    copilot_comments: list[dict[str, Any]]
    rag_context: list[dict[str, Any]]
    reflection_decision: str
    mentor_feedback: str
    learning_points: list[dict[str, Any]]
    structured_insights: list[dict[str, Any]]


def create_initial_state(
    pr_data: dict[str, Any],
    ci_findings: dict[str, Any],
    copilot_comments: list[dict[str, Any]],
    rag_context: list[dict[str, Any]] | None = None,
) -> ReviewState:
    return {
        "pr_data": pr_data,
        "ci_findings": ci_findings,
        "copilot_comments": copilot_comments,
        "rag_context": rag_context or [],
        "reflection_decision": "",
        "mentor_feedback": "",
        "learning_points": [],
    }
