from __future__ import annotations

import main as main_module
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from codementor.api.dependencies import get_llm_client
from codementor.api.templating import templates
from codementor.config import get_config
from codementor.github.client import GitHubClientError
from codementor.llm import LLMClientError

router = APIRouter()


@router.post("/review", response_class=HTMLResponse)
async def create_review(
    request: Request,
    mode: str = Form("mock"),
    owner: str | None = Form(None),
    repo: str | None = Form(None),
    pr_number: int | None = Form(None),
) -> HTMLResponse:
    config = get_config()
    llm_client = get_llm_client(config, config.llm_enabled)

    if mode == "github" and not (owner and repo and pr_number):
        return templates.TemplateResponse(
            request,
            "_error.html",
            {
                "message": "owner, repo und pr_number sind für den github-Modus erforderlich.",
            },
            status_code=400,
        )

    try:
        if mode == "github":
            result = main_module.run_github(
                owner, repo, pr_number, llm_client=llm_client
            )
        else:
            result = main_module.run_mock(llm_client=llm_client)
    except (GitHubClientError, LLMClientError) as exc:
        return templates.TemplateResponse(
            request, "_error.html", {"message": str(exc)}, status_code=502
        )

    thread_id = result["thread_id"]
    redirect_url = f"/threads/{thread_id}"
    return templates.TemplateResponse(
        request,
        "_review_result.html",
        {"thread_id": thread_id},
        headers={"HX-Redirect": redirect_url},
    )
