from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from typing import Any, cast

from codementor.llm import BaseLLMClient, MockLLMClient
from codementor.models import (
    ClassifiedCopilotComment,
    CopilotCategory,
    ReflectionDecision,
    parse_reflection_decision,
)
from codementor.state import ReviewState


CATEGORY_BY_ISSUE: dict[str, set[CopilotCategory]] = {
    "testing": {"testing", "bug_risk"},
    "typing": {"typing", "bug_risk"},
    "code_quality": {"readability", "architecture"},
    "copilot_review": {"bug_risk", "testing", "readability", "typing", "architecture"},
}


DOC_LINKS: dict[CopilotCategory, str] = {
    "bug_risk": "https://docs.python.org/3/tutorial/errors.html",
    "testing": "https://docs.pytest.org/en/stable/how-to/fixtures.html",
    "readability": "https://refactoring.guru/refactoring",
    "typing": "https://mypy.readthedocs.io/en/stable/kinds_of_types.html",
    "architecture": "https://docs.python-guide.org/writing/structure/",
}


def classify_copilot_comment(comment: dict[str, Any]) -> ClassifiedCopilotComment:
    text = str(comment.get("comment", ""))
    lowered = text.lower()
    file = str(comment.get("file", "unknown"))
    category: CopilotCategory

    if any(word in lowered for word in ("type", "mypy", "optional", "none")):
        category = "typing"
    elif any(word in lowered for word in ("test", "pytest", "fixture", "regression")):
        category = "testing"
    elif any(word in lowered for word in ("bug", "runtime", "exception", "crash")):
        category = "bug_risk"
    elif any(word in lowered for word in ("module", "boundary", "responsibility", "architecture")):
        category = "architecture"
    elif any(word in lowered for word in ("readability", "name", "simplify", "clearer")):
        category = "readability"
    elif file.startswith("tests/"):
        category = "testing"
    else:
        category = "readability"

    return ClassifiedCopilotComment(
        file=file,
        line=comment.get("line"),
        comment=text,
        severity=comment.get("severity"),
        category=category,
    )


def classify_copilot_comments(
    comments: list[dict[str, Any]],
    decision: ReflectionDecision,
) -> list[ClassifiedCopilotComment]:
    relevant_categories = CATEGORY_BY_ISSUE[decision.primary_issue]
    classified = []
    for comment in comments:
        item = classify_copilot_comment(comment)
        item.relevant = item.category in relevant_categories or item.severity == "high"
        classified.append(item)
    return classified


def build_dev_mentor_prompt(
    state: ReviewState,
    decision: ReflectionDecision,
    classified_comments: list[ClassifiedCopilotComment],
) -> str:
    # 1. RAG Kontext sicher extrahieren und für das LLM lesbar machen
    rag_data = state.get("rag_context", [])
    rag_summary = "\n".join([f"- {d['text']}" for d in rag_data]) if rag_data else "Kein zusätzlicher Kontext verfügbar."
    
    payload = {
        "reflection_decision": decision.model_dump(),
        "changed_files": state["pr_data"].get("changed_files", []),
        "ci_findings": state["ci_findings"],
        # Wir übergeben die zusammengefasste Summary, damit das Prompt-Token-Limit geschont wird
        "rag_summary": rag_summary, 
        "classified_copilot_comments": [
            comment.model_dump() for comment in classified_comments
        ],
        "structured_insights": state.get("structured_insights", {})
    }
    
    return (
f"Du bist ein geduldiger Mentor. Lernziel: {payload['structured_insights'].get('issue_category')}.\n"
        "RICHTLINIEN:\n"
        "- Fokus: Behandle AUSSCHLIESSLICH den Fehler in den PR-Dateien:\n"
        f"{json.dumps(state['pr_data'].get('changed_files', []), indent=2)}\n"
        "- Nutze das REFERENZ-WISSEN nur als allgemeine Hilfe, nicht als spezifische Lösung für andere Probleme.\n\n"
        "REFERENZ-WISSEN (RAG):\n"
        f"{rag_summary}\n\n"
        "OUTPUT:\n"
        "- Antworte in Markdown.\n"
        "- Strukturiere dein Feedback in: 'Observation', 'Socratic Question', 'Next Step'.\n"
        "CONTEXT:\n"
        f"{json.dumps(payload, sort_keys=True)}"
    )

def _format_file_focus(state: ReviewState) -> str:
    files = [item.get("path", "unknown") for item in state["pr_data"].get("changed_files", [])]
    if not files:
        return "No changed files were provided in the PR metadata."
    return ", ".join(files)


def _format_ci_focus(state: ReviewState) -> str:
    pytest_errors = state["ci_findings"].get("pytest", [])
    mypy_errors = state["ci_findings"].get("mypy", [])
    ruff_errors = state["ci_findings"].get("ruff", [])
    parts = []
    if pytest_errors:
        parts.append(f"{len(pytest_errors)} pytest failure(s)")
    if mypy_errors:
        parts.append(f"{len(mypy_errors)} mypy finding(s)")
    if ruff_errors:
        parts.append(f"{len(ruff_errors)} ruff finding(s)")
    return ", ".join(parts) if parts else "No CI findings were provided."


def _doc_hints(classified_comments: list[ClassifiedCopilotComment]) -> list[str]:
    categories = {comment.category for comment in classified_comments if comment.relevant}
    return [f"- {category}: {DOC_LINKS[category]}" for category in sorted(categories)]


def build_feedback(
    state: ReviewState,
    decision: ReflectionDecision,
    classified_comments: list[ClassifiedCopilotComment],
    llm_guidance: str,
) -> str:
    """
    Erstellt ein strukturiertes, didaktisch hochwertiges Review-Feedback im Markdown-Format.
    """
    # 1. Datenvorbereitung und Kontext-Extraktion
    insights = state.get("structured_insights", {})
    category = insights.get("issue_category", decision.primary_issue)
    
    # 2. Methodische Checkliste (dynamisch nach Kategorie)
    methodische_impulse = [
        f"- **Analyse:** Welche Annahme über den Code im Bereich `{category.upper()}` hat sich als kritisch erwiesen?",
        f"- **Prozess:** Wie könntest du mit dem aktuellen Test-Fokus ({category}) prüfen, ob dieser Fehler bei zukünftigen Änderungen erneut auftritt?",
        "- **Refactoring:** Welcher Refactoring-Schritt würde die Logik klarer machen, ohne den CI-Fehler zu 'verstecken'?"
    ]

    # 3. Copilot-Kommentare aufbereiten
    relevant = [comment for comment in classified_comments if comment.relevant]
    relevant_lines = [
        f"- `{comment.file}:{comment.line or '?'}` [{comment.category.upper()}] {comment.comment}"
        for comment in relevant
    ]

    # 4. Dokumentations-Hints
    docs = _doc_hints(classified_comments)
    if not docs:
        docs = ["keine spezifischen Dokumentations-Hinweise, da keine relevanten Copilot-Kommentare gefunden wurden."]

    # 5. Finale Markdown-Strukturierung
    output = "\n\n".join([
        "## 🎓 Mentor Feedback",
        f"**Fokus:** `{decision.primary_issue}` | **Schweregrad:** `{decision.severity.upper()}`",
        f"**Betroffene Dateien:** `{_format_file_focus(state)}` | **CI-Status:** `{_format_ci_focus(state)}`",

        "---",
        "### 🔍 Analyse der Anmerkungen",
        *(relevant_lines if relevant_lines else ["- *Keine kritischen Anmerkungen durch Copilot gefunden.*"]),

        "---",
        "### 🎙️ Individueller Mentor-Impuls",
        f"> {llm_guidance.strip()}",

        "---",
        "### 💡 Methodische Checkliste",
        *methodische_impulse,

        "---",
        "### 📚 Ressourcen & Dokumentation",
        *docs
    ])

    # 6. Artefakt-Sicherung (für Debugging/Protokollierung)
    with open("feedback.md", "w", encoding="utf-8") as f:
        f.write(output)

    return output

def run_dev_mentor_agent(
    state: ReviewState,
    llm: BaseLLMClient | None = None,
) -> tuple[str, list[ClassifiedCopilotComment]]:
    client = llm or MockLLMClient()
    decision = parse_reflection_decision(state["reflection_decision"])
    classified = classify_copilot_comments(state["copilot_comments"], decision)
    llm_guidance = client.generate(build_dev_mentor_prompt(state, decision, classified))
    return build_feedback(state, decision, classified, llm_guidance), classified


def dev_mentor_agent_node(llm: BaseLLMClient | None = None):
    def node(state: ReviewState) -> ReviewState:
        feedback, classified_comments = run_dev_mentor_agent(state, llm=llm)
        updated = deepcopy(state)
        updated["mentor_feedback"] = feedback
        updated["copilot_comments"] = [
            comment.model_dump(exclude_none=True) for comment in classified_comments
        ]
        return cast(ReviewState, updated)

    return node
