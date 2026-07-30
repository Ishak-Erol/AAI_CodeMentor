from __future__ import annotations

from codementor.agents.learning import learning_agent_node
from codementor.llm import BaseLLMClient


class EmptyLLM(BaseLLMClient):
    def generate(self, prompt: str) -> str:
        return "[]"


def test_learning_node_uses_feedback_fallback_when_llm_output_is_empty(
    review_state,
) -> None:
    """Liefert das LLM keine Lernpunkte, leitet der Learning Agent sie
    deterministisch aus dem Mentor-Feedback ab — ein Review endet nie ohne
    Lernpunkte."""
    review_state["mentor_feedback"] = (
        "pytest regression test and mypy Optional warning"
    )

    updated = learning_agent_node(EmptyLLM())(review_state)

    concepts = {point["concept"] for point in updated["learning_points"]}
    assert "pytest regression testing" in concepts
    assert "Optional-aware type checks" in concepts
