from __future__ import annotations

import json
from typing import Any

from codementor.db.models import LearningPoint, MiniTestat
from codementor.db.repository import (
    get_recent_learning_points,
    get_thread,
    get_thread_learning_points,
    save_mini_testat,
)
from codementor.llm import BaseLLMClient, MockLLMClient


def build_testat_prompt(points: list[LearningPoint]) -> str:
    concepts = [
        {"concept": point.concept, "difficulty": point.difficulty, "reason": point.reason}
        for point in points
    ]
    return (
        "Du bist ein Experte für Wissensüberprüfung. Erzeuge ein Mini-Testat mit "
        "2-3 offenen Prüfungsfragen zu den folgenden Lernkonzepten.\n"
        "REGELN:\n"
        "- Erzeuge zwischen 2 und 3 Fragen.\n"
        "- Jede Frage ist offen formuliert (keine Multiple-Choice) und bezieht sich "
        "auf ein konkretes Konzept aus dem CONTEXT.\n"
        "OUTPUT-SCHEMA (JSON): \n"
        "[{\"concept\": str, \"question\": str}]\n"
        f"CONTEXT:\n{json.dumps(concepts, sort_keys=True)}"
    )


def _fallback_questions(points: list[LearningPoint]) -> list[dict[str, str]]:
    fallback = [
        {
            "concept": point.concept,
            "question": (
                f"Erkläre das Konzept '{point.concept}' und wie du es im "
                "Review-Kontext angewendet hast."
            ),
        }
        for point in points[:3]
    ]
    if not fallback:
        fallback.append(
            {
                "concept": "review feedback triage",
                "question": (
                    "Wie gehst du vor, wenn du CI-Findings und Review-Kommentare "
                    "nach Risiko und Lernwert priorisieren musst?"
                ),
            }
        )
    return fallback


def _parse_testat_questions(
    raw_output: str, points: list[LearningPoint]
) -> list[dict[str, str]]:
    try:
        parsed = json.loads(raw_output)
    except (ValueError, TypeError):
        return _fallback_questions(points)

    if not isinstance(parsed, list):
        return _fallback_questions(points)

    questions: list[dict[str, str]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        question = item.get("question")
        if not isinstance(question, str) or not question.strip():
            continue
        questions.append(
            {"concept": str(item.get("concept", "")), "question": question}
        )

    if len(questions) < 2:
        return _fallback_questions(points)
    return questions[:3]


def generate_testat(
    thread_id: int, llm: BaseLLMClient | None = None
) -> MiniTestat | None:
    thread = get_thread(thread_id)
    if thread is None:
        raise ValueError(f"No thread found for thread_id={thread_id}")

    thread_points = get_thread_learning_points(thread_id)
    if not any(point.kind == "testat_suggestion" for point in thread_points):
        return None

    points = get_recent_learning_points(thread.student_id, limit_threads=3)

    client = llm or MockLLMClient()
    raw_output = client.generate(build_testat_prompt(points))
    questions: list[dict[str, Any]] = _parse_testat_questions(raw_output, points)

    return save_mini_testat(thread_id, questions)
