from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError


PrimaryIssue = Literal["testing", "typing", "code_quality", "copilot_review"]
Severity = Literal["low", "medium", "high"]
NextAgent = Literal["dev_mentor", "learning", "end"]
CopilotCategory = Literal["bug_risk", "testing", "readability", "typing", "architecture"]
Difficulty = Literal["easy", "medium", "hard"]
LearningPointKind = Literal["learning_point", "testat_suggestion"]


class ReflectionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_issue: PrimaryIssue
    severity: Severity
    next_agent: NextAgent


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


def parse_reflection_decision(raw_output: str) -> ReflectionDecision:
    try:
        return ReflectionDecision.model_validate_json(raw_output)
    except (ValidationError, ValueError, TypeError):
        return DEFAULT_REFLECTION_DECISION


def parse_learning_points(raw_output: str) -> list[LearningPoint]:
    adapter = TypeAdapter(list[LearningPoint])
    try:
        return adapter.validate_json(raw_output)
    except (ValidationError, ValueError, TypeError, json.JSONDecodeError):
        return []
