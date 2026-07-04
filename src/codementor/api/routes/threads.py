from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from codementor.api.dependencies import get_llm_client
from codementor.api.templating import templates
from codementor.config import get_config
from codementor.db.repository import (
    get_mini_testat,
    get_pull_request,
    get_thread,
    get_thread_agent_outputs,
    get_thread_learning_points,
    get_thread_messages,
    list_threads,
)
from codementor.threads import answer_follow_up

router = APIRouter()


@router.get("/threads", response_class=HTMLResponse)
async def threads_list(request: Request) -> HTMLResponse:
    threads = list_threads()
    return templates.TemplateResponse(
        request, "threads_list.html", {"threads": threads}
    )


@router.get("/threads/{thread_id}", response_class=HTMLResponse)
async def thread_detail(request: Request, thread_id: int) -> HTMLResponse:
    thread = get_thread(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    pull_request = get_pull_request(thread.pr_id)
    outputs = get_thread_agent_outputs(thread_id)
    dev_mentor_outputs = [output for output in outputs if output.agent == "dev_mentor"]
    mentor_feedback = dev_mentor_outputs[-1].content if dev_mentor_outputs else ""

    messages = get_thread_messages(thread_id)
    learning_points = get_thread_learning_points(thread_id)
    testat = get_mini_testat(thread_id)

    return templates.TemplateResponse(
        request,
        "thread_detail.html",
        {
            "thread": thread,
            "pull_request": pull_request,
            "mentor_feedback": mentor_feedback,
            "messages": messages,
            "learning_points": learning_points,
            "testat": testat,
        },
    )


@router.post("/threads/{thread_id}/ask", response_class=HTMLResponse)
async def ask_follow_up(
    request: Request, thread_id: int, question: str = Form("")
) -> HTMLResponse:
    question = question.strip()
    if not question:
        return templates.TemplateResponse(
            request,
            "_error.html",
            {"message": "Frage darf nicht leer sein."},
            status_code=400,
        )

    config = get_config()
    llm_client = get_llm_client(config, config.llm_enabled)
    answer_follow_up(thread_id, question, llm=llm_client)

    messages = get_thread_messages(thread_id)
    new_messages = messages[-2:]

    return templates.TemplateResponse(
        request, "_chat_message.html", {"messages": new_messages}
    )
