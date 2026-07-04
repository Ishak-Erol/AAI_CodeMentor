from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from codementor.api.templating import templates
from codementor.config import get_config
from codementor.db.engine import get_engine, init_db
from codementor.github.client import GitHubClientError
from codementor.llm import LLMClientError

PACKAGE_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = PACKAGE_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db(get_engine(get_config().db_path))
    yield


app = FastAPI(title="Team CodeMentor", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def read_index() -> RedirectResponse:
    return RedirectResponse(url="/threads")


@app.exception_handler(GitHubClientError)
async def handle_github_error(request: Request, exc: GitHubClientError) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "_error.html", {"message": str(exc)}, status_code=502
    )


@app.exception_handler(LLMClientError)
async def handle_llm_error(request: Request, exc: LLMClientError) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "_error.html", {"message": str(exc)}, status_code=502
    )


@app.exception_handler(ValueError)
async def handle_value_error(request: Request, exc: ValueError) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "_error.html", {"message": str(exc)}, status_code=400
    )


from codementor.api.routes.review import router as review_router  # noqa: E402
from codementor.api.routes.testat import router as testat_router  # noqa: E402
from codementor.api.routes.threads import router as threads_router  # noqa: E402

app.include_router(review_router)
app.include_router(threads_router)
app.include_router(testat_router)
