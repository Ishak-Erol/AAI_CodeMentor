from __future__ import annotations

import json
import logging
from typing import Any

from codementor.agents.dev_mentor import build_follow_up_prompt
from codementor.config import get_config
from codementor.db.models import ThreadMessage
from codementor.db.repository import (
    get_thread,
    get_thread_agent_outputs,
    get_thread_learning_points,
    get_thread_messages,
    save_concept_evidence,
    save_rag_citations,
    save_thread_message,
)
from codementor.llm import BaseLLMClient, NullLLMClient
from codementor.models import extract_json_snippet
from codementor.rag.embeddings import get_embedding_function
from codementor.rag.retriever import retrieve_context

logger = logging.getLogger(__name__)

VALID_OBSERVATION_VERDICTS = {"verstanden", "teilweise", "nicht_verstanden"}


MIN_RAG_QUERY_CHARS = 20


def _build_rag_query(question: str, prior_messages: list[ThreadMessage]) -> str:
    """Baut die Retrieval-Query aus der neuen Nachricht PLUS der letzten
    Mentor-Frage. Kurznachrichten wie "hi" oder "verstehe ich nicht" tragen
    selbst kein Thema — das Thema steckt in der Frage, auf die sie antworten.
    Ohne Themenbezug (zu kurze Query) wird gar nicht abgerufen, statt
    Zufallstreffer als "Quellen" auszuweisen."""
    mentor_messages = [
        m for m in prior_messages if m.role == "mentor" and m.content.strip()
    ]
    topic = mentor_messages[-1].content[:300] if mentor_messages else ""
    query = f"{question} {topic}".strip()
    return query if len(query) >= MIN_RAG_QUERY_CHARS else ""


def _retrieve_rag_results(query: str) -> list[dict[str, Any]]:
    config = get_config()
    if not config.rag_enabled or not query:
        return []
    try:
        embedding_function = get_embedding_function(config)
        return retrieve_context(
            query=query,
            persist_dir=config.rag_path,
            top_k=2,
            embedding_function=embedding_function,
            max_distance=config.rag_max_distance,
        )
    except Exception as exc:  # noqa: BLE001 — RAG-Ausfall darf den Chat nie brechen
        logger.warning("Chat-RAG übersprungen (%s).", exc)
        return []


def _summarize_rag_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return ""
    return "\n".join(f"- {item['text']}" for item in results)


def build_chat_observation_prompt(
    concepts: list[str], mentor_question: str, student_message: str
) -> str:
    payload = {
        "bekannte_konzepte": concepts,
        "letzte_mentor_frage": mentor_question,
        "studierenden_nachricht": student_message,
    }
    return (
        "Du bist ein stiller Beobachter in einem Lern-Chat. Prüfe, ob die Nachricht des "
        "Studierenden ein VERSTÄNDNIS-SIGNAL zu einem der bekannten Konzepte enthält.\n"
        "REGELN:\n"
        "- 'verdict' MUSS exakt einer dieser Werte sein: \"verstanden\" (die Nachricht "
        "erklärt das Konzept inhaltlich korrekt), \"teilweise\" (richtiger Ansatz, aber "
        "lückenhaft), \"nicht_verstanden\" (inhaltlich falsche Aussage über das Konzept) "
        "oder \"keine_aussage\".\n"
        "- 'keine_aussage' gilt IMMER, wenn die Nachricht nur eine Frage, ein Gruß, "
        "Ratlosigkeit ('weiß nicht') oder Smalltalk ist — eine Frage zu stellen ist KEIN "
        "Beleg für fehlendes Verständnis. Im Zweifel IMMER 'keine_aussage'.\n"
        "- 'concept' MUSS wörtlich eines der Konzepte aus 'bekannte_konzepte' sein, "
        "oder null bei 'keine_aussage'.\n"
        "- Antworte AUSSCHLIESSLICH mit dem JSON-Objekt, ohne Text davor oder danach.\n"
        "OUTPUT-SCHEMA (JSON): \n"
        "{\"concept\": str | null, \"verdict\": \"verstanden\" | \"teilweise\" | "
        "\"nicht_verstanden\" | \"keine_aussage\", \"begruendung\": str}\n"
        f"CONTEXT:\n{json.dumps(payload, sort_keys=True)}"
    )


def _observe_chat_evidence(
    thread_id: int,
    prior_messages: list[ThreadMessage],
    student_message: str,
    llm: BaseLLMClient,
) -> None:
    """Bewertet still, ob die Studierenden-Nachricht Verständnis belegt, und
    speichert das als ConceptEvidence. Darf den Chat NIE zum Scheitern bringen —
    jeder Fehler wird geschluckt und nur geloggt."""
    concepts = [
        point.concept
        for point in get_thread_learning_points(thread_id)
        if point.kind == "learning_point"
    ]
    if not concepts:
        return

    mentor_messages = [m for m in prior_messages if m.role == "mentor"]
    mentor_question = mentor_messages[-1].content if mentor_messages else ""

    raw = llm.generate(
        build_chat_observation_prompt(concepts, mentor_question, student_message)
    )
    for candidate in (raw, extract_json_snippet(raw)):
        try:
            parsed = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if not isinstance(parsed, dict):
            continue
        concept = parsed.get("concept")
        verdict = parsed.get("verdict")
        if (
            verdict in VALID_OBSERVATION_VERDICTS
            and isinstance(concept, str)
            and concept in concepts
        ):
            save_concept_evidence(
                thread_id=thread_id,
                concept=concept,
                assessment=verdict,
                note=str(parsed.get("begruendung", "")).strip()[:500],
            )
        return


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

    rag_results = _retrieve_rag_results(_build_rag_query(question, prior_messages))
    rag_summary = _summarize_rag_results(rag_results)
    client = llm or NullLLMClient()
    prompt = build_follow_up_prompt(
        original_feedback, prior_messages, question, rag_summary=rag_summary
    )
    answer = client.generate(prompt)

    mentor_message = save_thread_message(thread_id, role="mentor", content=answer)

    if rag_results:
        save_rag_citations(thread_id, rag_results, message_id=mentor_message.id)

    try:
        _observe_chat_evidence(thread_id, prior_messages, question, client)
    except Exception as exc:  # noqa: BLE001 — Beobachtung darf den Chat nie brechen
        logger.warning("Chat-Beobachtung übersprungen (thread %s): %s", thread_id, exc)

    return mentor_message
