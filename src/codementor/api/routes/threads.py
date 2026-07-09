from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from codementor.api.dependencies import get_llm_client
from codementor.api.templating import templates
from codementor.config import get_config
from codementor.db.models import RagCitation
from codementor.db.repository import (
    get_mini_testat,
    get_pull_request,
    get_thread,
    get_thread_agent_outputs,
    get_thread_citations,
    get_thread_learning_points,
    get_thread_messages,
    list_threads,
)
from codementor.student_profile import summarize_student_profile
from codementor.threads import answer_follow_up

router = APIRouter()


def _group_citations_by_message(
    citations: list[RagCitation],
) -> dict[int, list[RagCitation]]:
    grouped: dict[int, list[RagCitation]] = {}
    for citation in citations:
        if citation.message_id is not None:
            grouped.setdefault(citation.message_id, []).append(citation)
    return grouped


@router.get("/threads", response_class=HTMLResponse)
async def threads_list(request: Request) -> HTMLResponse:
    threads = list_threads()
    # PR-Titel zur Anzeige: "Thread #17" allein sagt nichts. Ein PR kann mehrere
    # Threads haben, daher pro pr_id nur einmal nachschlagen.
    pr_titles: dict[int, str] = {}
    for thread in threads:
        if thread.pr_id not in pr_titles:
            pull_request = get_pull_request(thread.pr_id)
            pr_titles[thread.pr_id] = pull_request.title if pull_request else ""
    return templates.TemplateResponse(
        request, "threads_list.html", {"threads": threads, "pr_titles": pr_titles}
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

    citations = get_thread_citations(thread_id)
    feedback_citations = [c for c in citations if c.message_id is None]
    citations_by_message = _group_citations_by_message(citations)

    student_profile = summarize_student_profile(thread.student_id)

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
            "feedback_citations": feedback_citations,
            "citations_by_message": citations_by_message,
            "student_profile": student_profile,
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

    citations = get_thread_citations(thread_id)
    citations_by_message = _group_citations_by_message(citations)

    return templates.TemplateResponse(
        request,
        "_chat_message.html",
        {"messages": new_messages, "citations_by_message": citations_by_message},
    )
