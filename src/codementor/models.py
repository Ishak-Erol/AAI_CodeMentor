from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

PrimaryIssue = Literal["testing", "typing", "code_quality", "copilot_review"]
Severity = Literal["low", "medium", "high"]
NextAgent = Literal["dev_mentor", "learning", "end"]
CopilotCategory = Literal["bug_risk", "testing", "readability", "typing", "architecture"]
Difficulty = Literal["easy", "medium", "hard"]
LearningPointKind = Literal["learning_point", "testat_suggestion"]


class ReflectionDecision(BaseModel):
    # extra="ignore" (not "forbid"): the reflection prompt asks the LLM for an
    # additional "reasoning" field to encourage better chain-of-thought before
    # answering, but that field isn't part of the persisted decision shape.
    model_config = ConfigDict(extra="ignore")

    primary_issue: PrimaryIssue
    severity: Severity
    next_agent: NextAgent
    # Deterministically computed (not LLM-decided) in reflection.py from real CI
    # findings / review comments. Drives dynamic graph routing: dev_mentor uses a
    # different, honesty-first prompt and the learning agent is skipped entirely
    # when there is nothing concrete to ground feedback in.
    has_concrete_evidence: bool = True


class ClassifiedCopilotComment(BaseModel):
    model_config = ConfigDict(extra="allow")

    file: str
    line: int | None = None
    comment: str
    severity: Severity | None = None
    category: CopilotCategory
    relevant: bool = True


class LearningPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept: str = Field(min_length=1)
    difficulty: Difficulty
    reason: str = Field(min_length=1)
    kind: LearningPointKind = "learning_point"


DEFAULT_REFLECTION_DECISION = ReflectionDecision(
    primary_issue="code_quality",
    severity="medium",
    next_agent="dev_mentor",
)


_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_JSON_SNIPPET_RE = re.compile(r"[\[{].*[\]}]", re.DOTALL)


def extract_json_snippet(raw_output: str) -> str:
    """Best-effort extraction of the JSON payload from an LLM response that may
    wrap valid JSON in explanatory prose or a markdown code fence."""
    text = raw_output.strip()
    fence_match = _CODE_FENCE_RE.search(text)
    if fence_match:
        return fence_match.group(1).strip()
    snippet_match = _JSON_SNIPPET_RE.search(text)
    if snippet_match:
        return snippet_match.group(0)
    return text


def parse_reflection_decision(raw_output: str) -> ReflectionDecision:
    try:
        return ReflectionDecision.model_validate_json(raw_output)
    except (ValidationError, ValueError, TypeError):
        pass
    try:
        return ReflectionDecision.model_validate_json(extract_json_snippet(raw_output))
    except (ValidationError, ValueError, TypeError):
        return DEFAULT_REFLECTION_DECISION


def parse_learning_points(raw_output: str) -> list[LearningPoint]:
    adapter = TypeAdapter(list[LearningPoint])
    try:
        return adapter.validate_json(raw_output)
    except (ValidationError, ValueError, TypeError, json.JSONDecodeError):
        pass
    try:
        return adapter.validate_json(extract_json_snippet(raw_output))
    except (ValidationError, ValueError, TypeError, json.JSONDecodeError):
        return []
