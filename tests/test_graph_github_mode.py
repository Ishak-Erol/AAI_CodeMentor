from __future__ import annotations

from codementor.graph import build_review_graph
from codementor.llm import BaseLLMClient
from codementor.models import parse_reflection_decision
from codementor.state import create_initial_state


class RoutingStub(BaseLLMClient):
    """Antwortet auf jeden Prompt mit einer festen Reflection-Entscheidung."""

    def generate(self, prompt: str) -> str:
        return (
            '{"primary_issue": "code_quality", "severity": "medium", '
            '"next_agent": "dev_mentor"}'
        )


def _github_style_state(diff: str, ci_findings: dict | None = None):
    pr_data = {
        "metadata": {
            "id": 1,
            "title": "Title",
            "description": "Body",
            "author": "dev",
            "source_branch": "feature",
            "target_branch": "main",
        },
        "learning_context": {},
        "changed_files": [{"path": "src/app.py", "status": "modified", "diff": diff}],
    }
    return create_initial_state(
        pr_data,
        ci_findings or {"ruff": [], "mypy": [], "pytest": []},
        [],
    )


def test_graph_ends_early_for_trivial_github_pr() -> None:
    """Grüne CI und keine substanzielle Code-Änderung: der Graph beendet sich,
    ohne Feedback zu erzeugen. Das ist gewollt — siehe die Trivial-Guardrail in
    `run_reflection_agent`."""
    graph = build_review_graph(llm=RoutingStub())

    final_state = graph.invoke(_github_style_state(diff=""))

    decision = parse_reflection_decision(final_state["reflection_decision"])
    assert decision.next_agent == "end"
    assert not final_state["learning_points"]


def test_graph_produces_feedback_for_github_pr_with_ci_findings() -> None:
    """Mit echtem CI-Befund läuft die Kette durch und erzeugt Mentor-Feedback
    samt Lernpunkten."""
    graph = build_review_graph(llm=RoutingStub())
    state = _github_style_state(
        diff="+def divide(a, b):\n+    return a / b",
        ci_findings={
            "ruff": [],
            "mypy": [],
            "pytest": [
                {
                    "test": "tests/test_app.py::test_divide_by_zero",
                    "message": "ZeroDivisionError: division by zero",
                    "traceback": "return a / b",
                }
            ],
        },
    )

    final_state = graph.invoke(state)

    assert final_state["mentor_feedback"]
    assert final_state["learning_points"]
