from __future__ import annotations

from copy import deepcopy
from typing import cast

from langgraph.graph import END, StateGraph

from codementor.agents.dev_mentor import dev_mentor_agent_node
from codementor.agents.learning import learning_agent_node
from codementor.agents.reflection import reflection_agent_node
from codementor.llm import BaseLLMClient, MockLLMClient
from codementor.models import parse_reflection_decision
from codementor.state import ReviewState


def orchestrator_node(state: ReviewState) -> ReviewState:
    updated = deepcopy(state)
    updated.setdefault("reflection_decision", "")
    updated.setdefault("mentor_feedback", "")
    updated.setdefault("learning_points", [])
    updated.setdefault("copilot_comments", [])
    return cast(ReviewState, updated)


def route_from_orchestrator(state: ReviewState) -> str:
    return "reflection"


def route_after_reflection(state: ReviewState) -> str:
    decision = parse_reflection_decision(state["reflection_decision"])
    return decision.next_agent


def build_review_graph(llm: BaseLLMClient | None = None):
    client = llm or MockLLMClient()
    graph = StateGraph(ReviewState)
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("reflection_agent", reflection_agent_node(client))
    graph.add_node("dev_mentor_agent", dev_mentor_agent_node(client))
    graph.add_node("learning_agent", learning_agent_node(client))

    graph.set_entry_point("orchestrator")
    graph.add_conditional_edges(
        "orchestrator",
        route_from_orchestrator,
        {"reflection": "reflection_agent"},
    )
    graph.add_conditional_edges(
        "reflection_agent",
        route_after_reflection,
        {
            "dev_mentor": "dev_mentor_agent",
            "learning": "learning_agent",
            "end": END,
        },
    )
    graph.add_edge("dev_mentor_agent", "learning_agent")
    graph.add_edge("learning_agent", END)
    return graph.compile()
