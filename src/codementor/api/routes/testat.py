from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from codementor.api.templating import templates
from codementor.db.repository import get_mini_testat, get_thread
from codementor.testat import generate_testat

router = APIRouter()


@router.get("/threads/{thread_id}/testat", response_class=HTMLResponse)
async def view_testat(request: Request, thread_id: int) -> HTMLResponse:
    thread = get_thread(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    testat = get_mini_testat(thread_id)
    questions = json.loads(testat.questions_json) if testat else []
    return templates.TemplateResponse(
        request,
        "testat.html",
        {"thread": thread, "testat": testat, "questions": questions},
    )


@router.post("/threads/{thread_id}/testat/generate", response_class=HTMLResponse)
async def trigger_testat(request: Request, thread_id: int) -> HTMLResponse:
    thread = get_thread(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    testat = generate_testat(thread_id)
    questions = json.loads(testat.questions_json) if testat else []
    return templates.TemplateResponse(
        request,
        "_testat_body.html",
        {"thread": thread, "testat": testat, "questions": questions},
    )
