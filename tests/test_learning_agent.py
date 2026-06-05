from __future__ import annotations

from codementor.agents.learning import learning_agent_node, run_learning_agent
from codementor.agents.dev_mentor import dev_mentor_agent_node
from codementor.agents.reflection import reflection_agent_node
from codementor.llm import BaseLLMClient, MockLLMClient
from codementor.mock_loader import load_mock_review_state


class EmptyLLM(BaseLLMClient):
    def generate(self, prompt: str) -> str:
        return "[]"


def test_learning_agent_extracts_structured_points_and_testat_suggestion() -> None:
    state = load_mock_review_state()
    state = reflection_agent_node(MockLLMClient())(state)
    state = dev_mentor_agent_node(MockLLMClient())(state)

    points = run_learning_agent(state, llm=MockLLMClient())

    concepts = {point.concept for point in points}
    assert "pytest fixtures" in concepts
    assert "mypy Optional handling" in concepts
    assert any(point.kind == "testat_suggestion" for point in points)


def test_learning_node_uses_feedback_fallback_when_llm_output_is_empty() -> None:
    state = load_mock_review_state()
    state["mentor_feedback"] = "pytest regression test and mypy Optional warning"

    updated = learning_agent_node(EmptyLLM())(state)

    concepts = {point["concept"] for point in updated["learning_points"]}
    assert "pytest regression testing" in concepts
    assert "Optional-aware type checks" in concepts
