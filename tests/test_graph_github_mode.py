from __future__ import annotations

from codementor.graph import build_review_graph
from codementor.llm import MockLLMClient
from codementor.state import create_initial_state


def test_graph_runs_with_github_style_state() -> None:
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
        "changed_files": [{"path": "src/app.py", "status": "modified", "diff": ""}],
    }
    state = create_initial_state(pr_data, {"ruff": [], "mypy": [], "pytest": []}, [])
    graph = build_review_graph(llm=MockLLMClient())

    final_state = graph.invoke(state)

    assert final_state["mentor_feedback"]
    assert final_state["learning_points"]
