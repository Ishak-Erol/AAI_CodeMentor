from __future__ import annotations

import json

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from codementor.api.dependencies import get_llm_client
from codementor.api.templating import templates
from codementor.config import get_config
from codementor.db.models import MiniTestat, TestatAnswer
from codementor.db.repository import get_mini_testat, get_testat_answers, get_thread
from codementor.testat import assess_testat_answer, generate_testat

router = APIRouter()


def _testat_context(testat: MiniTestat | None) -> dict:
    questions = json.loads(testat.questions_json) if testat else []
    answers: dict[int, TestatAnswer] = {}
    if testat:
        for record in get_testat_answers(testat.id):
            # Bei Mehrfach-Antworten zählt die jüngste (Liste ist chronologisch)
            answers[record.question_index] = record
    return {"testat": testat, "questions": questions, "answers": answers}


@router.get("/threads/{thread_id}/testat", response_class=HTMLResponse)
async def view_testat(request: Request, thread_id: int) -> HTMLResponse:
    thread = get_thread(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    testat = get_mini_testat(thread_id)
    return templates.TemplateResponse(
        request,
        "testat.html",
        {"thread": thread, **_testat_context(testat)},
    )


@router.post("/threads/{thread_id}/testat/generate", response_class=HTMLResponse)
async def trigger_testat(request: Request, thread_id: int) -> HTMLResponse:
    thread = get_thread(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    testat = generate_testat(thread_id)
    return templates.TemplateResponse(
        request,
        "_testat_body.html",
        {"thread": thread, **_testat_context(testat)},
    )


@router.post("/threads/{thread_id}/testat/answer", response_class=HTMLResponse)
async def answer_testat_question(
    request: Request,
    thread_id: int,
    question_index: int = Form(...),
    answer: str = Form(""),
) -> HTMLResponse:
    answer = answer.strip()
    if not answer:
        return templates.TemplateResponse(
            request,
            "_error.html",
            {"message": "Antwort darf nicht leer sein."},
            status_code=400,
        )

    testat = get_mini_testat(thread_id)
    if testat is None:
        raise HTTPException(
            status_code=404, detail=f"No testat found for thread {thread_id}"
        )

    config = get_config()
    llm_client = get_llm_client(config, config.llm_enabled)
    record = assess_testat_answer(testat, question_index, answer, llm=llm_client)

    questions = json.loads(testat.questions_json)
    return templates.TemplateResponse(
        request,
        "_testat_answer.html",
        {
            "thread_id": thread_id,
            "question": questions[question_index],
            "question_index": question_index,
            "record": record,
        },
    )
