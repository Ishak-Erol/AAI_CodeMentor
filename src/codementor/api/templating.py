from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

from codementor.api.markdown_utils import render_markdown

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["markdown"] = render_markdown
