from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, cast

from pydantic import ValidationError

from codementor.llm import BaseLLMClient, MockLLMClient
from codementor.models import LearningPoint, parse_learning_points
from codementor.state import ReviewState


def build_learning_prompt(state: ReviewState) -> str:
    payload = {
        "mentor_feedback": state["mentor_feedback"],
        "existing_learning_points": state["learning_points"],
        "learning_context": state["pr_data"].get("learning_context", {}),
        "rag_context": state.get("rag_context", []),
    }
    return (
"Du bist ein Experte für Knowledge-Management. Deine Aufgabe ist es, aus dem Mentor-Feedback konkrete Lernziele zu extrahieren.\n"
        "REGELN:\n"
        "- Extrahiere maximal 3 klare Lernpunkte.\n"
        "- 'difficulty' soll ein Wert zwischen 1 und 5 sein.\n"
        "OUTPUT-SCHEMA (JSON): \n"
        "[{\"concept\": str, \"difficulty\": int, \"reason\": str}]\n"
        f"CONTEXT:\n{json.dumps(payload, sort_keys=True)}"
    )


def fallback_learning_points(feedback: str) -> list[LearningPoint]:
    lowered = feedback.lower()
    points: list[LearningPoint] = []
    if "pytest" in lowered or "regression test" in lowered:
        points.append(
            LearningPoint(
                concept="pytest regression testing",
                difficulty="medium",
                reason="The feedback asks the learner to connect a failing CI case to a missing test.",
            )
        )
    if "mypy" in lowered or "optional" in lowered:
        points.append(
            LearningPoint(
                concept="Optional-aware type checks",
                difficulty="medium",
                reason="The feedback highlights a value that may be None before it is used.",
            )
        )
    if not points:
        points.append(
            LearningPoint(
                concept="review feedback triage",
                difficulty="easy",
                reason="The feedback requires sorting comments by risk and learning value.",
            )
        )
    return points


def _validated_existing_points(raw_points: list[dict[str, Any]]) -> list[LearningPoint]:
    validated: list[LearningPoint] = []
    for point in raw_points:
        try:
            validated.append(LearningPoint.model_validate(point))
        except ValidationError:
            continue
    return validated


def _dedupe_points(points: list[LearningPoint]) -> list[LearningPoint]:
    seen: set[str] = set()
    unique: list[LearningPoint] = []
    for point in points:
        key = point.concept.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(point)
    return unique


def _thread_count_after_current_review(state: ReviewState) -> int:
    context = state["pr_data"].get("learning_context", {})
    previous_threads = context.get("threads_reviewed")
    if isinstance(previous_threads, int):
        return previous_threads + 1
    return len(state["learning_points"]) + 1


def _maybe_add_testat_suggestion(
    points: list[LearningPoint],
    thread_count: int,
) -> list[LearningPoint]:
    has_suggestion = any(point.kind == "testat_suggestion" for point in points)
    if thread_count >= 3 and not has_suggestion:
        points.append(
            LearningPoint(
                concept="Testat proposal: CI-guided review basics",
                difficulty="medium",
                reason=(
                    "The learner has reached three review threads and can be checked "
                    "on testing, typing, and review-comment triage."
                ),
                kind="testat_suggestion",
            )
        )
    return points


def run_learning_agent(
    state: ReviewState,
    llm: BaseLLMClient | None = None,
) -> list[LearningPoint]:
    client = llm or MockLLMClient()
    raw_output = client.generate(build_learning_prompt(state))
    new_points = parse_learning_points(raw_output)
    if not new_points:
        new_points = fallback_learning_points(state["mentor_feedback"])

    existing_points = _validated_existing_points(state["learning_points"])
    combined = _dedupe_points([*existing_points, *new_points])
    return _maybe_add_testat_suggestion(
        combined,
        thread_count=_thread_count_after_current_review(state),
    )


def learning_agent_node(llm: BaseLLMClient | None = None):
    def node(state: ReviewState) -> ReviewState:
        learning_points = run_learning_agent(state, llm=llm)
        updated = deepcopy(state)
        updated["learning_points"] = [
            point.model_dump() for point in learning_points
        ]
        return cast(ReviewState, updated)

    return node
