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
        "copilot_comment_count": len(state["copilot_comments"]),
        "rag_context": state.get("rag_context", []),
    }
    return (
        "AGENT: reflection\n"
        "Decide the primary PR issue and return only valid JSON matching "
        "primary_issue, severity, needs_copilot_analysis, and next_agent.\n"
        f"CONTEXT:\n{json.dumps(payload, sort_keys=True)}"
    )


def run_reflection_agent(
    state: ReviewState,
    llm: BaseLLMClient | None = None,
) -> ReflectionDecision:
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
