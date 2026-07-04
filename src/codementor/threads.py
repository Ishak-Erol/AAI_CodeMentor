from __future__ import annotations

from typing import Any

from codementor.agents.dev_mentor import build_follow_up_prompt
from codementor.config import get_config
from codementor.db.models import ThreadMessage
from codementor.db.repository import (
    get_thread,
    get_thread_agent_outputs,
    get_thread_messages,
    save_rag_citations,
    save_thread_message,
)
from codementor.llm import BaseLLMClient, MockLLMClient
from codementor.rag.embeddings import get_embedding_function
from codementor.rag.retriever import retrieve_context


def _retrieve_rag_results(question: str) -> list[dict[str, Any]]:
    config = get_config()
    if not config.rag_enabled:
        return []
    embedding_function = get_embedding_function(config)
    return retrieve_context(
        query=question,
        persist_dir=config.rag_path,
        top_k=2,
        embedding_function=embedding_function,
    )


def _summarize_rag_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return ""
    return "\n".join(f"- {item['text']}" for item in results)


def answer_follow_up(
    thread_id: int,
    question: str,
    llm: BaseLLMClient | None = None,
) -> ThreadMessage:
    thread = get_thread(thread_id)
    if thread is None:
        raise ValueError(f"No thread found for thread_id={thread_id}")

    agent_outputs = get_thread_agent_outputs(thread_id)
    dev_mentor_outputs = [
        output for output in agent_outputs if output.agent == "dev_mentor"
    ]
    original_feedback = dev_mentor_outputs[-1].content if dev_mentor_outputs else ""

    prior_messages = get_thread_messages(thread_id)

    save_thread_message(thread_id, role="student", content=question)

    rag_results = _retrieve_rag_results(question)
    rag_summary = _summarize_rag_results(rag_results)
    client = llm or MockLLMClient()
    prompt = build_follow_up_prompt(
        original_feedback, prior_messages, question, rag_summary=rag_summary
    )
    answer = client.generate(prompt)

    mentor_message = save_thread_message(thread_id, role="mentor", content=answer)

    if rag_results:
        save_rag_citations(thread_id, rag_results, message_id=mentor_message.id)

    return mentor_message
