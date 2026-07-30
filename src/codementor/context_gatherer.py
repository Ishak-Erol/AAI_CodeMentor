from __future__ import annotations

import logging
import re
from typing import Any

from codementor.github.client import GitHubClient

logger = logging.getLogger(__name__)

# Entfernte Python-Funktionsdefinitionen im Diff (Zeilen, die mit "-" beginnen)
_REMOVED_DEF_RE = re.compile(r"^-\s*def\s+([A-Za-z_]\w*)\s*\(", re.MULTILINE)

MAX_REMOVED_FUNCTIONS = 3
MAX_FILES_TO_INSPECT = 2
MAX_FILE_CONTENT_CHARS = 3000


def plan_context_needs(pr_data: dict[str, Any]) -> dict[str, Any]:
    """Plan-Schritt: leitet deterministisch aus dem Diff ab, welcher Zusatz-Kontext
    für fundiertes Feedback fehlt. Bewusst Code statt LLM — welche Information
    fehlt, ist eine Faktenfrage, keine Ermessensfrage; so bleibt der Schritt auch
    mit kleinen Modellen zuverlässig. Das LLM argumentiert später nur noch über
    das, was der Execute-Schritt tatsächlich beschafft hat."""
    removed_functions: list[str] = []
    files_to_inspect: list[str] = []

    for changed_file in pr_data.get("changed_files", []):
        diff = str(changed_file.get("diff") or "")
        for name in _REMOVED_DEF_RE.findall(diff):
            if name not in removed_functions:
                removed_functions.append(name)
        path = str(changed_file.get("path") or "")
        if path.endswith(".py") and path not in files_to_inspect:
            files_to_inspect.append(path)

    return {
        "removed_functions": removed_functions[:MAX_REMOVED_FUNCTIONS],
        "files_to_inspect": files_to_inspect[:MAX_FILES_TO_INSPECT],
    }


def gather_context(
    pr_data: dict[str, Any],
    client: GitHubClient,
    owner: str,
    repo: str,
) -> dict[str, Any]:
    """Execute-Schritt: beschafft den geplanten Kontext über die GitHub-API.
    Jede einzelne Beschaffung darf fehlschlagen (Rate-Limit, nicht indexiert, ...),
    ohne den Review-Lauf zu gefährden — dann fehlt nur dieser eine Baustein."""
    needs = plan_context_needs(pr_data)
    gathered: dict[str, Any] = {
        "plan": needs,
        "removed_function_references": [],
        "file_contents": [],
    }

    for name in needs["removed_functions"]:
        try:
            hits = client.search_code(owner, repo, name)
        except Exception as exc:  # noqa: BLE001 — einzelner Ausfall ist ok
            logger.warning("Code-Suche für '%s' übersprungen: %s", name, exc)
            continue
        gathered["removed_function_references"].append(
            {
                "function": name,
                "reference_count": len(hits),
                "paths": [str(hit.get("path")) for hit in hits[:5]],
                # GitHub-Code-Suche indexiert den Default-Branch, nicht den
                # PR-Head — Treffer heißen also "auf main noch referenziert".
                "basis": "default-branch",
            }
        )

    head_sha = pr_data.get("metadata", {}).get("head_sha")
    for path in needs["files_to_inspect"]:
        try:
            content = client.get_file_content(owner, repo, path, ref=head_sha)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Dateiinhalt für '%s' übersprungen: %s", path, exc)
            continue
        gathered["file_contents"].append(
            {"path": path, "content": content[:MAX_FILE_CONTENT_CHARS]}
        )

    return gathered
