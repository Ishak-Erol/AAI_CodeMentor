from __future__ import annotations

import json
from typing import Any

from codementor.config import get_config
from codementor.db.engine import get_engine, init_db
from codementor.db.models import ReviewThread
from codementor.db.repository import (
    count_completed_threads,
    create_thread,
    get_or_create_pull_request,
    save_agent_output,
    save_learning_points,
)
from codementor.models import LearningPoint, parse_reflection_decision
from codementor.testat import generate_testat


def sync_learning_context(state: dict[str, Any]) -> dict[str, Any]:
    """Overwrites the mock/dev `learning_context.threads_reviewed` field with the
    real, per-student completed-thread count from the DB before the graph runs.

    This is the only place that bridges the mock/dev pr_data payload with the
    persisted thread count, so `_thread_count_after_current_review` in the
    learning agent operates on real data instead of the mock's hardcoded value.
    """
    init_db(get_engine(get_config().db_path))
    student_id = state["pr_data"].get("metadata", {}).get("author") or "unknown"
    learning_context = state["pr_data"].setdefault("learning_context", {})
    learning_context["threads_reviewed"] = count_completed_threads(student_id)
    return state


def persist_review_run(
    owner: str,
    repo: str,
    pr_number: int,
    title: str,
    final_state: dict[str, Any],
) -> ReviewThread:
    init_db(get_engine(get_config().db_path))
    pull_request = get_or_create_pull_request(owner, repo, pr_number, title)

    student_id = final_state["pr_data"].get("metadata", {}).get("author") or "unknown"

    decision = parse_reflection_decision(final_state["reflection_decision"])
    thread = create_thread(
        pr_id=pull_request.id,
        primary_issue=decision.primary_issue,
        severity=decision.severity,
        student_id=student_id,
    )

    save_agent_output(thread.id, "reflection", final_state["reflection_decision"])
    save_agent_output(thread.id, "dev_mentor", final_state["mentor_feedback"])
    save_agent_output(
        thread.id, "learning", json.dumps(final_state["learning_points"])
    )

    learning_points = [
        LearningPoint.model_validate(point) for point in final_state["learning_points"]
    ]
    save_learning_points(thread.id, learning_points)

    if any(point.kind == "testat_suggestion" for point in learning_points):
        generate_testat(thread.id)

    return thread
