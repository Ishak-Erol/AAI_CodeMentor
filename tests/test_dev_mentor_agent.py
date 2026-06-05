from __future__ import annotations

from codementor.agents.dev_mentor import dev_mentor_agent_node, run_dev_mentor_agent
from codementor.agents.reflection import reflection_agent_node
from codementor.llm import MockLLMClient
from codementor.mock_loader import load_mock_review_state


def test_dev_mentor_classifies_copilot_comments_and_builds_feedback() -> None:
    state = load_mock_review_state()
    state = reflection_agent_node(MockLLMClient())(state)

    feedback, classified = run_dev_mentor_agent(state, llm=MockLLMClient())

    assert "Guiding questions" in feedback
    assert "tests/test_review_parser.py" in feedback
    assert "https://docs.pytest.org" in feedback
    assert "Copilot comments classified" in feedback
    assert any(comment.category == "testing" for comment in classified)
    assert any(comment.category == "typing" for comment in classified)


def test_dev_mentor_node_updates_state_with_feedback_and_categories() -> None:
    state = load_mock_review_state()
    state = reflection_agent_node(MockLLMClient())(state)

    updated = dev_mentor_agent_node(MockLLMClient())(state)

    assert updated["mentor_feedback"].startswith("Mentor Feedback")
    assert all("category" in comment for comment in updated["copilot_comments"])
