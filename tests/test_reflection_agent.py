from __future__ import annotations

from codementor.agents.reflection import run_reflection_agent
from codementor.llm import BaseLLMClient, NullLLMClient
from codementor.state import create_initial_state


class InvalidLLM(BaseLLMClient):
    def generate(self, prompt: str) -> str:
        return "not-json"


def test_reflection_agent_uses_safe_fallback_for_invalid_output(review_state) -> None:
    """Liefert das LLM kein verwertbares JSON, muss der Reflection Agent auf eine
    gültige, konservative Entscheidung zurückfallen statt zu crashen."""
    decision = run_reflection_agent(review_state, llm=InvalidLLM())

    assert decision.primary_issue == "code_quality"
    assert decision.severity == "medium"
    assert decision.next_agent == "dev_mentor"


def test_reflection_agent_marks_ci_findings_as_concrete_evidence(review_state) -> None:
    """`has_concrete_evidence` wird deterministisch im Code bestimmt, nicht vom
    LLM — CI-Findings zählen als belastbare Evidenz."""
    review_state["ci_findings"] = {
        "ruff": [
            {
                "file": "src/review_parser.py",
                "line": 22,
                "code": "B904",
                "message": "raise exceptions with context",
            }
        ],
        "mypy": [],
        "pytest": [],
    }

    decision = run_reflection_agent(review_state, llm=NullLLMClient())

    assert decision.has_concrete_evidence is True


def test_reflection_agent_ends_chain_for_trivial_changes() -> None:
    """Guardrail: grüne CI plus rein kommentierte Änderungen dürfen keine
    Feedback-Kette auslösen (kein unnötiges Rauschen)."""
    state = create_initial_state(
        pr_data={
            "metadata": {"id": 1, "title": "Docstring ergänzt"},
            "learning_context": {},
            "changed_files": [
                {
                    "path": "src/app.py",
                    "status": "modified",
                    "diff": "+# erklärt den Zweck der Funktion",
                }
            ],
        },
        ci_findings={"ruff": [], "mypy": [], "pytest": []},
        copilot_comments=[],
    )

    decision = run_reflection_agent(state, llm=NullLLMClient())

    assert decision.next_agent == "end"
    assert decision.severity == "low"
    assert decision.has_concrete_evidence is False
