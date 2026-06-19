from __future__ import annotations

import json
from copy import deepcopy
from typing import cast

from codementor.llm import BaseLLMClient, MockLLMClient
from codementor.models import ReflectionDecision, parse_reflection_decision
from codementor.state import ReviewState


def build_reflection_prompt(state: ReviewState) -> str:
    payload = {
        "pr_data": state["pr_data"],
        "ci_findings": state["ci_findings"],
        "structured_insights": state.get("structured_insights", {}),
        "copilot_comment_count": len(state["copilot_comments"]),
        "rag_context": state.get("rag_context", []),
    }
    return (
        "Du bist ein Senior-Architekt, der Pull-Requests auf Architektur-Risiken und Komplexität prüft.\n\n"
        "🚨 STRIKTE PRIORITÄTS-REGEL (CRITICAL):\n"
        "Wenn alle CI-Checks (pytest, ruff, mypy) vollständig GRÜN (leer) sind und NUR Kommentare, Docstrings oder Typos hinzugefügt/geändert wurden, MUSS der nächste Agent 'end' sein! Erzeuge kein unnötiges Rauschen, wenn der Code funktional korrekt und sauber ist.\n\n"
        "DEINE AUFGABE:\n"
        "1. Analysiere das primary_issue und severity (Low, Medium, High) basierend auf den CI-Findings und Code-Änderungen.\n"
        "2. Wähle den nächsten Agenten basierend auf diesen STRIKTEN KRITERIEN:\n\n"
        "PFAD 'dev_mentor':\n"
        "- Komplexe Logik geändert (Algorithmen, Transaktionen).\n"
        "- Kritische Code Smells, handfeste Bugs oder echte Architekturverstöße erkennbar.\n"
        "- CI-Fehler sind schwer zu interpretieren und erfordern Refactoring.\n\n"
        "PFAD 'learning':\n"
        "- Code ist funktional korrekt und CI ist grün, aber es gibt unsaubere Idiomatik oder leicht redundante Kommentare (Meckern auf hohem Niveau).\n"
        "- Nur kleine Best-Practice-Tipps nötig.\n\n"
        "PFAD 'end':\n"
        "- PR-Daten zeigen NUR triviale Änderungen (Typos, reine Dokumentation, Kommentare).\n"
        "- CI ist komplett grün und der Code funktioniert tadellos.\n"
        "- Jedes weitere Eingreifen wäre reine Zeitverschwendung.\n\n"
        "FORMAT:\n"
        "Antworte AUSSCHLIESSLICH als JSON:\n"
        "{\"primary_issue\": str, \"severity\": str, \"next_agent\": \"dev_mentor\"|\"learning\"|\"end\", \"reasoning\": str}\n\n"
        f"CONTEXT:\n{json.dumps(payload, sort_keys=True)}"
    )

def run_reflection_agent(
    state: ReviewState,
    llm: BaseLLMClient | None = None,
) -> ReflectionDecision:
    # 🚨 DETEKTIERE TRIVIALE ÄNDERUNGEN DIREKT (GUARDRAIL)
    ci = state.get("ci_findings", {})
    is_ci_clean = not (ci.get("ruff") or ci.get("mypy") or ci.get("pytest"))
    
    changed_files = state["pr_data"].get("changed_files", [])
    only_comments_or_empty = True
    for f in changed_files:
        diff_lines = f.get("diff", "").split("\n")
        for line in diff_lines:
            if line.startswith("+") and not line.startswith("+++"):
                cleaned = line[1:].strip()
                if cleaned and not cleaned.startswith("#"):
                    only_comments_or_empty = False
                    break

    # Wenn CI grün ist und nur Kommentare geändert wurden -> Pydantic-konformer Abbruch
    if is_ci_clean and only_comments_or_empty:
        return ReflectionDecision(
            primary_issue="code_quality",  # Erlaubtes Literal
            severity="low",                # Niedriger Schweregrad
            next_agent="end"               # Kette sauber beenden (ohne verbotenes 'reasoning' Feld)
        )

    # Normaler LLM-Pfad für echte Code-Änderungen
    client = llm or MockLLMClient()
    raw_output = client.generate(build_reflection_prompt(state))
    return parse_reflection_decision(raw_output)

def reflection_agent_node(llm: BaseLLMClient | None = None):
    def node(state: ReviewState) -> ReviewState:
        decision = run_reflection_agent(state, llm=llm)
        updated = deepcopy(state)
        updated["reflection_decision"] = decision.model_dump_json()
        return cast(ReviewState, updated)

    return node
