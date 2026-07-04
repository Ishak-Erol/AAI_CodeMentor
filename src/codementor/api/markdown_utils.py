from __future__ import annotations

import markdown as _markdown


def render_markdown(text: str) -> str:
    if not text:
        return ""
    return _markdown.markdown(text, extensions=["fenced_code", "tables"])
