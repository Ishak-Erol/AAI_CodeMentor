from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from codementor.api.templating import templates
from codementor.db.repository import (
    get_student_assessments,
    get_student_concept_evidence,
    list_threads,
)
from codementor.student_profile import summarize_student_profile

router = APIRouter()

_STATUS_LABELS = {
    "mastered": "verstanden",
    "struggling": "noch offen",
    "repeated": "mehrfach gesehen",
    "seen": "gesehen",
}


@router.get("/students/{student_id}", response_class=HTMLResponse)
async def student_journey(request: Request, student_id: str) -> HTMLResponse:
    threads = list_threads(limit=10_000, student_id=student_id)
    if not threads:
        raise HTTPException(
            status_code=404, detail=f"Keine Review-Threads für '{student_id}' gefunden"
        )
    threads_chronological = sorted(threads, key=lambda thread: thread.created_at)

    profile = summarize_student_profile(student_id)

    # Alle Verständnis-Signale (Testat + Chat) chronologisch, pro Konzept gebündelt
    signals = [
        (record.timestamp, record.concept, record.assessment, "Testat")
        for record in get_student_assessments(student_id)
    ] + [
        (record.timestamp, record.concept, record.assessment, "Chat")
        for record in get_student_concept_evidence(student_id)
    ]
    signals.sort(key=lambda item: item[0])

    last_signal: dict[str, dict[str, Any]] = {}
    history: dict[str, list[str]] = {}
    for timestamp, concept, assessment, source in signals:
        last_signal[concept] = {
            "assessment": assessment,
            "source": source,
            "timestamp": timestamp,
        }
        history.setdefault(concept, []).append(assessment)

    concepts: list[dict[str, Any]] = []
    for concept, count in profile["seen_concepts"].items():
        if concept in profile["mastered_concepts"]:
            status = "mastered"
        elif concept in profile["struggling_concepts"]:
            status = "struggling"
        elif concept in profile["repeated_concepts"]:
            status = "repeated"
        else:
            status = "seen"
        concepts.append(
            {
                "name": concept,
                "count": count,
                "status": status,
                "status_label": _STATUS_LABELS[status],
                "last": last_signal.get(concept),
                "history": history.get(concept, []),
            }
        )
    # Offene Konzepte zuerst — das ist die Arbeitsliste des Studierenden
    status_order = {"struggling": 0, "repeated": 1, "seen": 2, "mastered": 3}
    concepts.sort(key=lambda item: (status_order[item["status"]], item["name"]))

    return templates.TemplateResponse(
        request,
        "student_journey.html",
        {
            "student_id": student_id,
            "profile": profile,
            "concepts": concepts,
            "threads": threads_chronological,
        },
    )
