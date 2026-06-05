from __future__ import annotations

from html.parser import HTMLParser
from typing import Iterable

import httpx


DEFAULT_DOC_URLS = [
    "https://docs.python.org/3/",
    "https://docs.astral.sh/ruff/",
    "https://mypy.readthedocs.io/en/stable/",
    "https://docs.pytest.org/en/stable/",
]


class HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._text_parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = False

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = data.strip()
        if text:
            self._text_parts.append(text)

    def get_text(self) -> str:
        return " ".join(self._text_parts)


def _extract_text_from_html(html: str) -> str:
    parser = HTMLTextExtractor()
    parser.feed(html)
    return parser.get_text()


def fetch_url_text(url: str, timeout: float = 20.0) -> str:
    response = httpx.get(url, timeout=timeout)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if "text/html" in content_type:
        return _extract_text_from_html(response.text)
    return response.text


def ensure_doc_urls(urls: Iterable[str] | None) -> list[str]:
    if not urls:
        return DEFAULT_DOC_URLS.copy()
    return [item for item in (str(url).strip() for url in urls) if item]
