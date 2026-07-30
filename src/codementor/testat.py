from __future__ import annotations

import json
from typing import Any

from codementor.db.models import MiniTestat, TestatAnswer
from codementor.db.repository import (
    get_recent_learning_points,
    get_thread,
    get_thread_learning_points,
    save_mini_testat,
    save_testat_answer,
)
from codementor.llm import BaseLLMClient, NullLLMClient
from codementor.models import extract_json_snippet
from codementor.student_profile import summarize_student_profile

VALID_ASSESSMENTS = {"verstanden", "teilweise", "nicht_verstanden"}


def _build_testat_entries(student_id: str) -> list[dict[str, str]]:
    """Stellt die Konzept-Kandidaten fürs Testat zusammen, lernstand-gesteuert:

    1. Offene Konzepte (im letzten Testat/Chat "nicht verstanden") kommen ZUERST
       als Wiederholungsfragen — ein offenes Konzept ohne zweite Chance wäre
       eine tote Remediation-Schleife.
    2. Bereits nachweislich verstandene Konzepte werden NICHT erneut geprüft.
    3. Danach neue, noch ungeprüfte Konzepte aus den letzten Reviews.
    """
    profile = summarize_student_profile(student_id)
    struggling = list(profile.get("struggling_concepts", []))
    mastered = set(profile.get("mastered_concepts", []))

    recent_by_concept: dict[str, Any] = {}
    for point in get_recent_learning_points(student_id, limit_threads=3):
        if point.kind != "learning_point":
            continue
        recent_by_concept.setdefault(point.concept, point)

    entries: list[dict[str, str]] = []
    for concept in struggling:
        point = recent_by_concept.get(concept)
        entries.append(
            {
                "concept": concept,
                "difficulty": point.difficulty if point else "medium",
                "reason": "Beim letzten Testat/Chat noch nicht sicher beantwortet.",
                "status": "wiederholung",
            }
        )
    for concept, point in recent_by_concept.items():
        if concept in mastered or concept in struggling:
            continue
        entries.append(
            {
                "concept": concept,
                "difficulty": point.difficulty,
                "reason": point.reason,
                "status": "neu",
            }
        )

    if not entries:
        # Alles gemeistert (oder gar keine Punkte): Auffrischung statt leerem Testat
        entries = [
            {
                "concept": point.concept,
                "difficulty": point.difficulty,
                "reason": point.reason,
                "status": "neu",
            }
            for point in recent_by_concept.values()
        ]
    return entries


def build_testat_prompt(entries: list[dict[str, str]]) -> str:
    return (
        "Du bist ein Experte für Wissensüberprüfung. Erzeuge ein Mini-Testat mit "
        "2-3 offenen Prüfungsfragen zu den folgenden Lernkonzepten.\n"
        "REGELN:\n"
        "- Erzeuge zwischen 2 und 3 Fragen.\n"
        "- Konzepte mit status='wiederholung' wurden zuvor NICHT sicher beantwortet: "
        "Stelle zu diesen ZUERST je eine Frage, und zwar aus einem NEUEN Blickwinkel "
        "(nicht dieselbe Formulierung wie eine frühere Frage), damit echtes Verständnis "
        "geprüft wird statt Wiedererkennen.\n"
        "- Jede Frage ist offen formuliert (keine Multiple-Choice) und bezieht sich "
        "auf ein konkretes Konzept aus dem CONTEXT.\n"
        "- Antworte AUSSCHLIESSLICH mit dem JSON-Array, ohne einleitenden oder erklärenden "
        "Text davor oder danach, und ohne Markdown-Codeblock.\n"
        "OUTPUT-SCHEMA (JSON): \n"
        "[{\"concept\": str, \"question\": str}]\n"
        f"CONTEXT:\n{json.dumps(entries, sort_keys=True)}"
    )


def _fallback_questions(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    fallback = []
    for entry in entries[:3]:
        if entry.get("status") == "wiederholung":
            question = (
                f"Beim letzten Mal blieb '{entry['concept']}' noch offen: Erkläre das "
                "Konzept in eigenen Worten und nenne ein konkretes Beispiel aus deinem Code."
            )
        else:
            question = (
                f"Erkläre das Konzept '{entry['concept']}' und wie du es im "
                "Review-Kontext angewendet hast."
            )
        fallback.append({"concept": entry["concept"], "question": question})
    if not fallback:
        fallback.append(
            {
                "concept": "review feedback triage",
                "question": (
                    "Wie gehst du vor, wenn du CI-Findings und Review-Kommentare "
                    "nach Risiko und Lernwert priorisieren musst?"
                ),
            }
        )
    return fallback


def _parse_testat_questions(
    raw_output: str, entries: list[dict[str, str]]
) -> list[dict[str, str]]:
    try:
        parsed = json.loads(raw_output)
    except (ValueError, TypeError):
        try:
            parsed = json.loads(extract_json_snippet(raw_output))
        except (ValueError, TypeError):
            return _fallback_questions(entries)

    if not isinstance(parsed, list):
        return _fallback_questions(entries)

    questions: list[dict[str, str]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        question = item.get("question")
        if not isinstance(question, str) or not question.strip():
            continue
        questions.append(
            {"concept": str(item.get("concept", "")), "question": question}
        )

    if len(questions) < 2:
        return _fallback_questions(entries)
    return questions[:3]


def generate_testat(
    thread_id: int, llm: BaseLLMClient | None = None
) -> MiniTestat | None:
    thread = get_thread(thread_id)
    if thread is None:
        raise ValueError(f"No thread found for thread_id={thread_id}")

    thread_points = get_thread_learning_points(thread_id)
    if not any(point.kind == "testat_suggestion" for point in thread_points):
        return None

    entries = _build_testat_entries(thread.student_id)

    client = llm or NullLLMClient()
    raw_output = client.generate(build_testat_prompt(entries))
    questions: list[dict[str, Any]] = _parse_testat_questions(raw_output, entries)

    return save_mini_testat(thread_id, questions)


def build_assessment_prompt(concept: str, question: str, answer: str) -> str:
    payload = {"concept": concept, "question": question, "answer": answer}
    return (
        "Du bist ein wohlwollender, aber ehrlicher Prüfer. Bewerte die Antwort eines "
        "Studierenden auf eine offene Prüfungsfrage.\n"
        "REGELN:\n"
        "- 'assessment' MUSS exakt einer dieser drei Werte sein: \"verstanden\" (Kernidee "
        "korrekt erfasst, kleine Lücken sind okay), \"teilweise\" (richtige Ansätze, aber "
        "wesentliche Aspekte fehlen oder sind unklar) oder \"nicht_verstanden\" (Antwort geht "
        "am Konzept vorbei, ist leer-formelhaft oder faktisch falsch).\n"
        "- 'feedback': 2-4 Sätze. Benenne zuerst konkret, was an der Antwort richtig ist "
        "(falls etwas), dann was fehlt oder falsch ist. Bei 'nicht_verstanden' erkläre das "
        "Konzept kurz in einfachen Worten, damit der Studierende daraus lernt — ein Testat "
        "darf auflösen, es ist der Abschluss des Lernzyklus.\n"
        "- Bewerte den INHALT, nicht Rechtschreibung oder Ausdruck. Sei nicht streng bei "
        "informeller Sprache.\n"
        "- Antworte AUSSCHLIESSLICH mit dem JSON-Objekt, ohne Text davor oder danach und "
        "ohne Markdown-Codeblock.\n"
        "OUTPUT-SCHEMA (JSON): \n"
        "{\"assessment\": \"verstanden\" | \"teilweise\" | \"nicht_verstanden\", \"feedback\": str}\n"
        f"CONTEXT:\n{json.dumps(payload, sort_keys=True)}"
    )


def _parse_assessment(raw_output: str) -> dict[str, str] | None:
    for candidate in (raw_output, extract_json_snippet(raw_output)):
        try:
            parsed = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if not isinstance(parsed, dict):
            continue
        assessment = parsed.get("assessment")
        feedback = parsed.get("feedback")
        if assessment in VALID_ASSESSMENTS and isinstance(feedback, str) and feedback.strip():
            return {"assessment": assessment, "feedback": feedback.strip()}
    return None


def assess_testat_answer(
    testat: MiniTestat,
    question_index: int,
    answer: str,
    llm: BaseLLMClient | None = None,
) -> TestatAnswer:
    questions = json.loads(testat.questions_json)
    if not (0 <= question_index < len(questions)):
        raise ValueError(f"Testat {testat.id} has no question at index {question_index}")
    question = questions[question_index]

    client = llm or NullLLMClient()
    raw_output = client.generate(
        build_assessment_prompt(
            concept=str(question.get("concept", "")),
            question=str(question.get("question", "")),
            answer=answer,
        )
    )

    parsed = _parse_assessment(raw_output)
    if parsed is None:
        # Konservativer Fallback: nie hart failen, aber auch keine Meisterschaft
        # attestieren, die das LLM nicht bestätigt hat.
        parsed = {
            "assessment": "teilweise",
            "feedback": (
                "Deine Antwort wurde gespeichert, konnte aber nicht automatisch "
                "bewertet werden. Besprich sie am besten kurz im Thread-Chat."
            ),
        }

    return save_testat_answer(
        testat_id=testat.id,
        question_index=question_index,
        concept=str(question.get("concept", "")),
        answer=answer,
        assessment=parsed["assessment"],
        feedback=parsed["feedback"],
    )
