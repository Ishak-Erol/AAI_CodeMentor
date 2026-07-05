from __future__ import annotations

import logging
from typing import Any

from codementor.config import AppConfig
from codementor.rag.indexer import _get_collection, index_documents


logger = logging.getLogger(__name__)

# Thema -> maßgebliche Doku-Startseite. Bewusst dieselben URLs wie in
# sources.DEFAULT_DOC_URLS: On-Demand-Indexierung ist das Sicherheitsnetz,
# falls eine Quelle beim Refresh fehlte (vergessen, Fetch-Fehler, alter Index).
TOPIC_SOURCES: dict[str, str] = {
    "github_actions": "https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax",
    "pytest": "https://docs.pytest.org/en/stable/how-to/fixtures.html",
    "mypy": "https://mypy.readthedocs.io/en/stable/kinds_of_types.html",
    "ruff": "https://docs.astral.sh/ruff/rules/",
    "python_errors": "https://docs.python.org/3/tutorial/errors.html",
}

# On-Demand läuft synchron im Review — kleinerer Crawl als beim expliziten Refresh
ON_DEMAND_MAX_PAGES = 5


def detect_topics(
    pr_data: dict[str, Any], ci_findings: dict[str, Any]
) -> list[str]:
    """Deterministische Themenerkennung aus PR-Inhalt und CI-Findings — Code
    statt LLM, weil "welches Thema berührt dieser PR" eine Faktenfrage ist."""
    topics: list[str] = []

    def _add(topic: str) -> None:
        if topic not in topics:
            topics.append(topic)

    for changed_file in pr_data.get("changed_files", []):
        path = str(changed_file.get("path") or "").lower()
        diff = str(changed_file.get("diff") or "")
        if ".github/workflows" in path or (
            path.endswith((".yml", ".yaml"))
            and any(marker in diff for marker in ("jobs:", "runs-on", "steps:"))
        ):
            _add("github_actions")
        name = path.rsplit("/", 1)[-1]
        if path.startswith("tests/") or name.startswith("test_"):
            _add("pytest")
        if path.endswith(".py"):
            _add("python_errors")

    if ci_findings.get("pytest"):
        _add("pytest")
    if ci_findings.get("mypy"):
        _add("mypy")
    if ci_findings.get("ruff"):
        _add("ruff")

    return topics


def _source_indexed(collection, url: str) -> bool:
    for key in ("root_source", "source"):
        try:
            existing = collection.get(where={key: url}, limit=1)
        except Exception:  # noqa: BLE001 — z.B. Legacy-Index ohne das Feld
            continue
        if existing.get("ids"):
            return True
    return False


def ensure_topic_sources(
    pr_data: dict[str, Any],
    ci_findings: dict[str, Any],
    config: AppConfig,
    embedding_function,
) -> list[str]:
    """Agentische Wissensbeschaffung: erkennt, welche Themen der PR berührt,
    prüft, ob der Index dazu überhaupt eine Quelle enthält, und indexiert
    fehlende Doku on-demand nach (kleiner Crawl, damit der Review-Lauf nicht
    lange blockiert). Gibt die nachindexierten URLs zurück; Fehler einzelner
    Quellen brechen den Review nie ab."""
    topics = detect_topics(pr_data, ci_findings)
    if not topics:
        return []

    collection = _get_collection(config.rag_path, embedding_function)
    added_sources: list[str] = []
    for topic in topics:
        url = TOPIC_SOURCES[topic]
        if _source_indexed(collection, url):
            continue
        logger.info(
            "Wissenslücke erkannt: Thema '%s' ohne Quelle im Index — hole %s nach",
            topic,
            url,
        )
        try:
            added = index_documents(
                [url],
                config.rag_path,
                embedding_function,
                refresh=False,
                max_pages_per_source=min(config.rag_max_pages, ON_DEMAND_MAX_PAGES),
            )
            if added:
                added_sources.append(url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("On-Demand-Indexierung für %s fehlgeschlagen: %s", url, exc)
    return added_sources
