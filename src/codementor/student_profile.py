from __future__ import annotations

from collections import Counter
from typing import Any

from codementor.config import get_config
from codementor.db.engine import get_engine, init_db
from codementor.db.models import LearningPoint
from codementor.db.repository import (
    count_completed_threads,
    get_student_assessments,
    get_thread_learning_points,
    list_threads,
)


def get_student_learning_history(student_id: str) -> list[LearningPoint]:
    init_db(get_engine(get_config().db_path))
    threads = list_threads(limit=10_000, student_id=student_id)
    threads_chronological = sorted(threads, key=lambda thread: thread.created_at)

    history: list[LearningPoint] = []
    for thread in threads_chronological:
        history.extend(get_thread_learning_points(thread.id))
    return history


def summarize_student_profile(student_id: str) -> dict[str, Any]:
    history = get_student_learning_history(student_id)
    seen_concepts = dict(Counter(point.concept for point in history))
    repeated_concepts = [
        concept for concept, count in seen_concepts.items() if count > 1
    ]

    # Testat-Antworten sind das einzige echte Verständnis-Signal: pro Konzept
    # zählt die JÜNGSTE Bewertung (Verständnis kann sich ändern; Antworten sind
    # bereits chronologisch sortiert, spätere überschreiben frühere).
    latest_assessment: dict[str, str] = {}
    for record in get_student_assessments(student_id):
        if record.concept:
            latest_assessment[record.concept] = record.assessment

    mastered_concepts = [
        concept
        for concept, assessment in latest_assessment.items()
        if assessment == "verstanden"
    ]
    struggling_concepts = [
        concept
        for concept, assessment in latest_assessment.items()
        if assessment == "nicht_verstanden"
    ]

    return {
        "seen_concepts": seen_concepts,
        "repeated_concepts": repeated_concepts,
        "mastered_concepts": mastered_concepts,
        "struggling_concepts": struggling_concepts,
        "total_threads": count_completed_threads(student_id),
    }
