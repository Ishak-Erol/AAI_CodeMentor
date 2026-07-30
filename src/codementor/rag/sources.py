from __future__ import annotations

import logging
from collections.abc import Iterable
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin

import httpx

logger = logging.getLogger(__name__)

# Bewusst tiefe, spezifische Seiten statt Doku-Startseiten. Über den
# Depth-1-Crawl (crawl_source) werden zusätzlich die intern verlinkten Seiten
# derselben Doku-Sektion indexiert — die Startseite definiert also die Sektion.
DEFAULT_DOC_URLS = [
    "https://docs.python.org/3/tutorial/errors.html",
    "https://docs.astral.sh/ruff/rules/",
    "https://mypy.readthedocs.io/en/stable/kinds_of_types.html",
    "https://docs.pytest.org/en/stable/how-to/fixtures.html",
    "https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax",
]

# Nicht-HTML-Ressourcen, die beim Crawlen übersprungen werden
_SKIP_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".zip", ".tar", ".gz", ".pdf", ".whl", ".js", ".css", ".xml",
)


class HTMLTextExtractor(HTMLParser):
    """Extrahiert lesbaren Text UND interne Links in einem Durchlauf."""

    def __init__(self) -> None:
        super().__init__()
        self._text_parts: list[str] = []
        self._skip = False
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = True
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value:
                    self.links.append(value)

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


def fetch_page(url: str, timeout: float = 20.0) -> tuple[str, list[str]]:
    """Holt eine Seite und liefert (Text, gefundene Links)."""
    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if "text/html" in content_type:
        parser = HTMLTextExtractor()
        parser.feed(response.text)
        return parser.get_text(), parser.links
    return response.text, []


def fetch_url_text(url: str, timeout: float = 20.0) -> str:
    text, _ = fetch_page(url, timeout=timeout)
    return text


def _section_prefix(start_url: str) -> str:
    """Die Doku-Sektion einer Start-URL: ihr Verzeichnis. Nur Links innerhalb
    dieser Sektion werden gecrawlt, damit z.B. docs.python.org nicht komplett
    eingesammelt wird."""
    if start_url.endswith("/"):
        return start_url
    return start_url.rsplit("/", 1)[0] + "/"


def crawl_source(
    start_url: str, max_pages: int, timeout: float = 20.0
) -> list[tuple[str, str]]:
    """Depth-1-Crawl: Startseite plus die von ihr aus verlinkten Seiten derselben
    Doku-Sektion, gedeckelt auf `max_pages` Seiten insgesamt. Liefert
    [(seiten_url, text), ...]; einzelne Fetch-Fehler werden übersprungen."""
    prefix = _section_prefix(start_url)
    pages: list[tuple[str, str]] = []

    try:
        text, links = fetch_page(start_url, timeout=timeout)
    except httpx.HTTPError as exc:
        logger.warning("Skipping RAG source %s (fetch failed: %s)", start_url, exc)
        return pages
    pages.append((start_url, text))

    visited = {start_url}
    for link in links:
        if len(pages) >= max_pages:
            break
        absolute = urldefrag(urljoin(start_url, link)).url
        if absolute in visited:
            continue
        if not absolute.startswith(prefix):
            continue
        if absolute.lower().endswith(_SKIP_EXTENSIONS):
            continue
        visited.add(absolute)
        try:
            sub_text, _ = fetch_page(absolute, timeout=timeout)
        except httpx.HTTPError as exc:
            logger.warning("Skipping crawled page %s (fetch failed: %s)", absolute, exc)
            continue
        pages.append((absolute, sub_text))

    return pages


def ensure_doc_urls(urls: Iterable[str] | None) -> list[str]:
    if not urls:
        return DEFAULT_DOC_URLS.copy()
    return [item for item in (str(url).strip() for url in urls) if item]
