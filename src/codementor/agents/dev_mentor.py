from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from typing import Any, cast

from codementor.llm import BaseLLMClient, MockLLMClient
from codementor.models import (
    ClassifiedCopilotComment,
    CopilotCategory,
    ReflectionDecision,
    parse_reflection_decision,
)
from codementor.state import ReviewState


CATEGORY_BY_ISSUE: dict[str, set[CopilotCategory]] = {
    "testing": {"testing", "bug_risk"},
    "typing": {"typing", "bug_risk"},
    "code_quality": {"readability", "architecture"},
    "copilot_review": {"bug_risk", "testing", "readability", "typing", "architecture"},
}


DOC_LINKS: dict[CopilotCategory, str] = {
    "bug_risk": "https://docs.python.org/3/tutorial/errors.html",
    "testing": "https://docs.pytest.org/en/stable/how-to/fixtures.html",
    "readability": "https://refactoring.guru/refactoring",
    "typing": "https://mypy.readthedocs.io/en/stable/kinds_of_types.html",
    "architecture": "https://docs.python-guide.org/writing/structure/",
}


def classify_copilot_comment(comment: dict[str, Any]) -> ClassifiedCopilotComment:
    text = str(comment.get("comment", ""))
    lowered = text.lower()
    file = str(comment.get("file", "unknown"))
    category: CopilotCategory

    if any(word in lowered for word in ("type", "mypy", "optional", "none")):
        category = "typing"
    elif any(word in lowered for word in ("test", "pytest", "fixture", "regression")):
        category = "testing"
    elif any(word in lowered for word in ("bug", "runtime", "exception", "crash")):
        category = "bug_risk"
    elif any(word in lowered for word in ("module", "boundary", "responsibility", "architecture")):
        category = "architecture"
    elif any(word in lowered for word in ("readability", "name", "simplify", "clearer")):
        category = "readability"
    elif file.startswith("tests/"):
        category = "testing"
    else:
        category = "readability"

    return ClassifiedCopilotComment(
        file=file,
        line=comment.get("line"),
        comment=text,
        severity=comment.get("severity"),
        category=category,
    )


def classify_copilot_comments(
    comments: list[dict[str, Any]],
    decision: ReflectionDecision,
) -> list[ClassifiedCopilotComment]:
    relevant_categories = CATEGORY_BY_ISSUE[decision.primary_issue]
    classified = []
    for comment in comments:
        item = classify_copilot_comment(comment)
        item.relevant = item.category in relevant_categories or item.severity == "high"
        classified.append(item)
    return classified


def build_dev_mentor_prompt(
    state: ReviewState,
    decision: ReflectionDecision,
    classified_comments: list[ClassifiedCopilotComment],
) -> str:
    payload = {
        "reflection_decision": decision.model_dump(),
        "changed_files": state["pr_data"].get("changed_files", []),
        "ci_findings": state["ci_findings"],
        "rag_context": state.get("rag_context", []),
        "classified_copilot_comments": [
            comment.model_dump() for comment in classified_comments
        ],
    }
    return (
        "AGENT: dev_mentor\n"
        "Create Socratic learning-oriented review feedback. Do not provide a full patch.\n"
        f"CONTEXT:\n{json.dumps(payload, sort_keys=True)}"
    )


def _format_file_focus(state: ReviewState) -> str:
    files = [item.get("path", "unknown") for item in state["pr_data"].get("changed_files", [])]
    if not files:
        return "No changed files were provided in the PR metadata."
    return ", ".join(files)


def _format_ci_focus(state: ReviewState) -> str:
    pytest_errors = state["ci_findings"].get("pytest", [])
    mypy_errors = state["ci_findings"].get("mypy", [])
    ruff_errors = state["ci_findings"].get("ruff", [])
    parts = []
    if pytest_errors:
        parts.append(f"{len(pytest_errors)} pytest failure(s)")
    if mypy_errors:
        parts.append(f"{len(mypy_errors)} mypy finding(s)")
    if ruff_errors:
        parts.append(f"{len(ruff_errors)} ruff finding(s)")
    return ", ".join(parts) if parts else "No CI findings were provided."


def _doc_hints(classified_comments: list[ClassifiedCopilotComment]) -> list[str]:
    categories = {comment.category for comment in classified_comments if comment.relevant}
    return [f"- {category}: {DOC_LINKS[category]}" for category in sorted(categories)]


def build_feedback(
    state: ReviewState,
    decision: ReflectionDecision,
    classified_comments: list[ClassifiedCopilotComment],
    llm_guidance: str,
) -> str:
    category_counts = Counter(comment.category for comment in classified_comments)
    relevant = [comment for comment in classified_comments if comment.relevant]
    relevant_lines = [
        f"- {comment.file}:{comment.line or '?'} [{comment.category}] {comment.comment}"
        for comment in relevant
    ]
    if not relevant_lines:
        relevant_lines = ["- No Copilot comments matched the current route strongly."]

    docs = _doc_hints(classified_comments)
    if not docs:
        docs = ["- review strategy: [internal docs placeholder]/reviewing-ci-feedback"]

    guidance = llm_guidance.strip() or (
        "Start from the strongest failing signal and ask for the smallest learning step."
    )

    return "\n".join(
        [
            "Mentor Feedback",
            f"Focus: {decision.primary_issue} ({decision.severity})",
            f"Changed areas: {_format_file_focus(state)}",
            f"CI signal: {_format_ci_focus(state)}",
            "",
            "Copilot comments classified:",
            *relevant_lines,
            f"Category summary: {dict(sorted(category_counts.items()))}",
            "",
            "Guiding questions:",
            "- Which missing regression test would make the failing pytest case obvious before CI runs?",
            "- What does the mypy Optional warning tell you about the parser's assumptions?",
            "- In the touched files, where can you add confidence without hiding the original CI signal?",
            "",
            "Documentation hints:",
            *docs,
            "",
            f"Mentor stance: {guidance}",
        ]
    )


def run_dev_mentor_agent(
    state: ReviewState,
    llm: BaseLLMClient | None = None,
) -> tuple[str, list[ClassifiedCopilotComment]]:
    client = llm or MockLLMClient()
    decision = parse_reflection_decision(state["reflection_decision"])
    classified = classify_copilot_comments(state["copilot_comments"], decision)
    llm_guidance = client.generate(build_dev_mentor_prompt(state, decision, classified))
    return build_feedback(state, decision, classified, llm_guidance), classified


def dev_mentor_agent_node(llm: BaseLLMClient | None = None):
    def node(state: ReviewState) -> ReviewState:
        feedback, classified_comments = run_dev_mentor_agent(state, llm=llm)
        updated = deepcopy(state)
        updated["mentor_feedback"] = feedback
        updated["copilot_comments"] = [
            comment.model_dump(exclude_none=True) for comment in classified_comments
        ]
        return cast(ReviewState, updated)

    return node
