from __future__ import annotations

from codementor.agents.dev_mentor import build_follow_up_prompt
from codementor.config import get_config
from codementor.db.models import ThreadMessage
from codementor.db.repository import (
    get_thread,
    get_thread_agent_outputs,
    get_thread_messages,
    save_thread_message,
)
from codementor.llm import BaseLLMClient, MockLLMClient
from codementor.rag.embeddings import get_embedding_function
from codementor.rag.retriever import retrieve_context


def _build_rag_summary(question: str) -> str:
    config = get_config()
    if not config.rag_enabled:
        return ""
    embedding_function = get_embedding_function(config)
    results = retrieve_context(
        query=question,
        persist_dir=config.rag_path,
        top_k=2,
        embedding_function=embedding_function,
    )
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

    rag_summary = _build_rag_summary(question)
    client = llm or MockLLMClient()
    prompt = build_follow_up_prompt(
        original_feedback, prior_messages, question, rag_summary=rag_summary
    )
    answer = client.generate(prompt)

    return save_thread_message(thread_id, role="mentor", content=answer)
