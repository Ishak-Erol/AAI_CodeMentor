from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

import main as main_module
from codementor.api.dependencies import get_llm_client
from codementor.api.templating import templates
from codementor.config import get_config
from codementor.github.client import GitHubClientError
from codementor.llm import LLMClientError

router = APIRouter()


@router.post("/review", response_class=HTMLResponse)
async def create_review(
    request: Request,
    owner: str | None = Form(None),
    repo: str | None = Form(None),
    pr_number: int | None = Form(None),
) -> HTMLResponse:
    config = get_config()

    if not (owner and repo and pr_number):
        return templates.TemplateResponse(
            request,
            "_error.html",
            {"message": "Owner, Repo und PR-Nummer sind erforderlich."},
            status_code=400,
        )

    # Reviews laufen ausschließlich live: Ohne LLM gäbe es nur leere
    # Mentor-Texte — das melden wir laut, statt still zu degradieren.
    if not config.llm_enabled:
        return templates.TemplateResponse(
            request,
            "_error.html",
            {
                "message": (
                    "Kein LLM konfiguriert: API_KEY setzen (z.B. .env laden mit "
                    "'set -a; source .env; set +a') und den Server neu starten."
                )
            },
            status_code=503,
        )

    llm_client = get_llm_client(config, True)

    try:
        result = main_module.run_github(
            owner,
            repo,
            pr_number,
            llm_client=llm_client,
            rag_enabled=config.rag_enabled,
        )
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
