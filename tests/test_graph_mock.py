from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from codementor.graph import build_review_graph
from codementor.llm import MockLLMClient
from codementor.mock_loader import MOCKS_DIR, load_json, load_mock_review_state
from codementor.models import parse_reflection_decision


ROOT = Path(__file__).resolve().parents[1]


def test_graph_runs_mock_pr_end_to_end() -> None:
    expected = load_json(MOCKS_DIR / "mock_feedback_output.json")
    graph = build_review_graph(llm=MockLLMClient())

    final_state = graph.invoke(load_mock_review_state())

    decision = parse_reflection_decision(final_state["reflection_decision"])
    assert decision.primary_issue == expected["expected_primary_issue"]
    assert final_state["mentor_feedback"]
    assert final_state["learning_points"]
    assert all("category" in comment for comment in final_state["copilot_comments"])
    for term in expected["required_feedback_terms"]:
        assert term in final_state["mentor_feedback"]
    concepts = {point["concept"] for point in final_state["learning_points"]}
    assert set(expected["expected_learning_concepts"]).issubset(concepts)
    assert any(point["kind"] == "testat_suggestion" for point in final_state["learning_points"])


def test_cli_mock_command_outputs_final_state_json() -> None:
    result = subprocess.run(
        [sys.executable, "main.py", "--mode", "mock"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    marker = "FINAL_STATE_JSON:\n"
    assert marker in result.stdout
    payload = result.stdout.split(marker, maxsplit=1)[1]
    final_state = json.loads(payload)
    assert final_state["mentor_feedback"]
    assert final_state["learning_points"]
