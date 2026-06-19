from __future__ import annotations

from codementor.agents.reflection import reflection_agent_node, run_reflection_agent
from codementor.llm import BaseLLMClient, MockLLMClient
from codementor.mock_loader import load_mock_review_state
from codementor.models import parse_reflection_decision


class InvalidLLM(BaseLLMClient):
    def generate(self, prompt: str) -> str:
        return "not-json"


def test_reflection_agent_returns_structured_testing_decision() -> None:
    state = load_mock_review_state()

    decision = run_reflection_agent(state, llm=MockLLMClient())

    assert decision.primary_issue == "testing"
    assert decision.severity == "high"
    assert decision.next_agent == "dev_mentor"


def test_reflection_node_stores_valid_json_decision() -> None:
    state = load_mock_review_state()

    updated = reflection_agent_node(MockLLMClient())(state)
    decision = parse_reflection_decision(updated["reflection_decision"])

    assert decision.primary_issue == "testing"


def test_reflection_agent_uses_safe_fallback_for_invalid_output() -> None:
    state = load_mock_review_state()

    decision = run_reflection_agent(state, llm=InvalidLLM())

    assert decision.primary_issue == "code_quality"
    assert decision.severity == "medium"
    assert decision.next_agent == "dev_mentor"


def test_reflection_agent_uses_ci_findings_instead_of_pr_keywords() -> None:
    state = load_mock_review_state()
    state["ci_findings"] = {
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

    decision = run_reflection_agent(state, llm=MockLLMClient())

    assert decision.primary_issue == "code_quality"
    assert decision.severity == "medium"
