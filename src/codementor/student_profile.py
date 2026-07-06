from __future__ import annotations

from collections import Counter
from typing import Any

from codementor.config import get_config
from codementor.db.engine import get_engine, init_db
from codementor.db.models import LearningPoint
from codementor.db.repository import (
    count_completed_threads,
    get_student_assessments,
    get_student_concept_evidence,
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
    # Nur echte Lernpunkte zählen — der interne "testat_suggestion"-Marker ist
    # ein Trigger, kein Lerninhalt, und darf weder im Fortschritt noch in den
    # Prompt-Hinweisen auftauchen.
    seen_concepts = dict(
        Counter(
            point.concept for point in history if point.kind == "learning_point"
        )
    )
    repeated_concepts = [
        concept for concept, count in seen_concepts.items() if count > 1
    ]

    # Verständnis-Signale kommen aus zwei Quellen: Testat-Antworten UND
    # Chat-Beobachtungen (wenn ein Studierender eine sokratische Frage im
    # Follow-up richtig beantwortet). Beide werden chronologisch zusammengeführt;
    # pro Konzept zählt die JÜNGSTE Bewertung, egal aus welcher Quelle.
    signals = [
        (record.timestamp, record.concept, record.assessment)
        for record in get_student_assessments(student_id)
    ] + [
        (record.timestamp, record.concept, record.assessment)
        for record in get_student_concept_evidence(student_id)
    ]
    latest_assessment: dict[str, str] = {}
    for _, concept, assessment in sorted(signals, key=lambda item: item[0]):
        if concept:
            latest_assessment[concept] = assessment

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
