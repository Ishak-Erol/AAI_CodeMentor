from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from typing import Any, cast

from codementor.db.models import ThreadMessage
from codementor.llm import BaseLLMClient, MockLLMClient
from codementor.models import (
    ClassifiedCopilotComment,
    CopilotCategory,
    ReflectionDecision,
    extract_json_snippet,
    parse_reflection_decision,
)
from codementor.state import ReviewState
from codementor.student_profile import summarize_student_profile


CATEGORY_BY_ISSUE: dict[str, set[CopilotCategory]] = {
    "testing": {"testing", "bug_risk"},
    "typing": {"typing", "bug_risk"},
    "code_quality": {"readability", "architecture"},
    "copilot_review": {"bug_risk", "testing", "readability", "typing", "architecture"},
}


DOC_LINKS: dict[CopilotCategory, str] = {
    "bug_risk": "https://docs.python.org/3/tutorial/errors.html",
    "testing": "https://docs.pytest.org/en/stable/how-to/fixtures.html",
    "readability": "https://refactoring.guru/refactoring",
    "typing": "https://mypy.readthedocs.io/en/stable/kinds_of_types.html",
    "architecture": "https://docs.python-guide.org/writing/structure/",
}


def classify_copilot_comment(comment: dict[str, Any]) -> ClassifiedCopilotComment:
    text = str(comment.get("comment", ""))
    lowered = text.lower()
    file = str(comment.get("file", "unknown"))
    category: CopilotCategory

    if any(word in lowered for word in ("type", "mypy", "optional", "none")):
        category = "typing"
    elif any(word in lowered for word in ("test", "pytest", "fixture", "regression")):
        category = "testing"
    elif any(word in lowered for word in ("bug", "runtime", "exception", "crash")):
        category = "bug_risk"
    elif any(word in lowered for word in ("module", "boundary", "responsibility", "architecture")):
        category = "architecture"
    elif any(word in lowered for word in ("readability", "name", "simplify", "clearer")):
        category = "readability"
    elif file.startswith("tests/"):
        category = "testing"
    else:
        category = "readability"

    return ClassifiedCopilotComment(
        file=file,
        line=comment.get("line"),
        comment=text,
        severity=comment.get("severity"),
        category=category,
    )


def classify_copilot_comments(
    comments: list[dict[str, Any]],
    decision: ReflectionDecision,
) -> list[ClassifiedCopilotComment]:
    relevant_categories = CATEGORY_BY_ISSUE[decision.primary_issue]
    classified = []
    for comment in comments:
        item = classify_copilot_comment(comment)
        item.relevant = item.category in relevant_categories or item.severity == "high"
        classified.append(item)
    return classified


def build_dev_mentor_prompt(
    state: ReviewState,
    decision: ReflectionDecision,
    classified_comments: list[ClassifiedCopilotComment],
    student_profile: dict[str, Any] | None = None,
) -> str:
    # 1. RAG Kontext sicher extrahieren und für das LLM lesbar machen
    rag_data = state.get("rag_context", [])
    rag_summary = "\n".join([f"- {d['text']}" for d in rag_data]) if rag_data else "Kein zusätzlicher Kontext verfügbar."

    # 2. Lernstand aus dem Studierendenprofil ableiten. Wichtig: "mehrfach gesehen"
    # heißt NICHT "verstanden" — nur bestandene Testat-Antworten belegen Verständnis.
    profile = student_profile or {}
    mastered = profile.get("mastered_concepts", [])
    struggling = profile.get("struggling_concepts", [])
    repeated_unproven = [
        concept
        for concept in profile.get("repeated_concepts", [])
        if concept not in mastered and concept not in struggling
    ]

    hint_parts: list[str] = []
    if mastered:
        hint_parts.append(
            f"NACHWEISLICH VERSTANDEN (im Testat belegt): {', '.join(mastered)}. "
            "Hier darfst du vertiefende, anspruchsvollere Fragen stellen und Grundlagen "
            "als bekannt voraussetzen."
        )
    if struggling:
        hint_parts.append(
            f"NOCH NICHT VERSTANDEN (im Testat nicht sicher beantwortet, obwohl schon "
            f"behandelt): {', '.join(struggling)}. Hier ist Wiederholung KEIN Zeichen von "
            "Wissen — erkläre einfacher und kleinschrittiger als beim letzten Mal, statt "
            "zu vertiefen, und setze nichts als bekannt voraus."
        )
    if repeated_unproven:
        hint_parts.append(
            f"MEHRFACH GEZEIGT, ABER NOCH NICHT GEPRÜFT: {', '.join(repeated_unproven)}. "
            "Knüpfe an die frühere Behandlung an ('wie beim letzten Review...'), aber setze "
            "das Konzept nicht als beherrscht voraus."
        )
    repetition_hint = (
        "\n".join(hint_parts)
        if hint_parts
        else "Noch kein Lernstand zu diesem Studierenden bekannt — behandle alle Konzepte als neu."
    )

    gathered_context = state.get("gathered_context") or {}

    payload = {
        "reflection_decision": decision.model_dump(),
        "changed_files": state["pr_data"].get("changed_files", []),
        "ci_findings": state["ci_findings"],
        # Wir übergeben die zusammengefasste Summary, damit das Prompt-Token-Limit geschont wird
        "rag_summary": rag_summary,
        "classified_copilot_comments": [
            comment.model_dump() for comment in classified_comments
        ],
        "structured_insights": state.get("structured_insights", {}),
        "student_profile": student_profile or {},
        "gathered_context": gathered_context,
    }

    if decision.has_concrete_evidence:
        output_instructions = (
            "- Strukturiere deine Antwort in GENAU diese vier Absätze, jeweils mit dem Label in "
            "Fettdruck als eigene Zeile:\n"
            "  **Was ist passiert:** 1-2 Sätze, was sich im Code konkret geändert hat (bezogen auf "
            "die tatsächlichen geänderten Dateien/Zeilen), und was daran auffällig ist.\n"
            "  **Warum das wichtig ist:** 2-4 Sätze ECHTE Erklärung des zugrunde liegenden Konzepts "
            "oder Risikos in einfachen Worten — KEINE Frage, sondern eine Erklärung. Der Studierende "
            "soll danach verstehen, WORUM es fachlich geht, auch wenn er die konkrete Lösung noch "
            "nicht kennt.\n"
            "  **Worüber du nachdenken solltest:** GENAU EINE konkrete, code-bezogene sokratische "
            "Frage (keine abstrakte Kategorie-Frage wie 'Welche Annahme hat sich als kritisch "
            "erwiesen?' ohne Bezug zum tatsächlichen Code), die den Studierenden zur eigenen Lösung "
            "führt.\n"
            "  **Nächster Schritt:** Ein konkreter, überprüfbarer Handlungsschritt (z.B. ein Befehl "
            "zum Ausführen, eine Zeile zum Anschauen, ein Test zum Schreiben) — keine allgemeine "
            "Floskel wie 'überprüfe, ob alles funktioniert'.\n"
            "- Gib an KEINER Stelle den fertigen Code-Fix oder die exakte Lösung für diesen PR preis "
            "— 'Warum das wichtig ist' erklärt das KONZEPT, nicht die Lösung für diesen konkreten Fall.\n"
        )
    else:
        output_instructions = (
            "- WICHTIG: Es liegen WEDER CI-Findings NOCH Review-Kommentare für diesen PR vor — du "
            "hast NUR den reinen Code-Diff als Anhaltspunkt. Erfinde KEINE hypothetischen "
            "Konsequenzen, Risiken oder Verhaltensweisen, die sich nicht direkt und offensichtlich "
            "aus dem Diff ablesen lassen (z.B. keine erfundenen Aussagen über CI-System-Verhalten, "
            "Performance oder Seiteneffekte, die dort nicht sichtbar sind).\n"
            "- Strukturiere deine Antwort in GENAU diese vier Absätze, jeweils mit dem Label in "
            "Fettdruck als eigene Zeile:\n"
            "  **Was ist passiert:** 1-2 Sätze, was sich im Code konkret geändert hat.\n"
            "  **Was noch unklar ist:** Benenne EHRLICH, was sich ohne CI-Lauf oder Review-"
            "Kommentar nicht beurteilen lässt (z.B. ob eine entfernte Funktion noch anderswo im "
            "Projekt aufgerufen wird, oder ob die Tests noch grün sind).\n"
            "  **Worüber du nachdenken solltest:** GENAU EINE konkrete Frage, die den "
            "Studierenden dazu bringt, das selbst zu überprüfen (z.B. im Repo nach Aufrufen "
            "einer entfernten Funktion zu suchen).\n"
            "  **Nächster Schritt:** Ein konkreter, selbst ausführbarer Check (z.B. 'führe die "
            "Tests lokal aus und schau, ob etwas fehlschlägt', 'durchsuche das Repo nach "
            "Aufrufen von X') — keine allgemeine Floskel.\n"
        )

    return (
f"Du bist ein geduldiger Mentor. Lernziel: {payload['structured_insights'].get('issue_category')}.\n"
        "RICHTLINIEN:\n"
        "- Fokus: Behandle AUSSCHLIESSLICH den Fehler in den PR-Dateien:\n"
        f"{json.dumps(state['pr_data'].get('changed_files', []), indent=2)}\n"
        "- Nutze das REFERENZ-WISSEN nur als allgemeine Hilfe, nicht als spezifische Lösung für andere Probleme.\n"
        "- Triff NUR technische Aussagen über Tool-/Syntax-Verhalten (z.B. was eine bestimmte "
        "CI-Konfigurationsoption oder Sprachfunktion bewirkt), die durch das REFERENZ-WISSEN (RAG) "
        "unten ODER direkt durch den gezeigten Diff belegt sind. Wenn du dir über das Verhalten "
        "eines Tools/einer Syntax-Option nicht sicher bist und weder RAG noch der Diff das "
        "eindeutig zeigen, sag das ehrlich (z.B. 'wie genau sich X auswirkt, lässt sich ohne "
        "weitere Doku nicht sicher sagen') statt eine plausibel klingende Vermutung zu erfinden.\n"
        "- VOM SYSTEM AUTOMATISCH BESCHAFFTER KONTEXT (siehe 'gathered_context' im CONTEXT): "
        "Wenn 'removed_function_references' einen Eintrag mit reference_count > 0 enthält, ist "
        "das ein KONKRETER Befund: Eine im PR entfernte Funktion wird auf dem Default-Branch "
        "noch an den gelisteten Stellen referenziert. Benenne das explizit und frage, ob diese "
        "Stellen im PR mitangepasst wurden. 'file_contents' (vollständige Dateiinhalte) darfst "
        "du nutzen, um deine Aussagen zu belegen.\n\n"
        "WIEDERHOLUNGS-HINWEIS (Studierendenprofil):\n"
        f"{repetition_hint}\n\n"
        "KONTINUITÄTS-REGEL:\n"
        "Wenn oben ein Konzept als 'NOCH NICHT VERSTANDEN' oder 'MEHRFACH GEZEIGT, ABER "
        "NOCH NICHT GEPRÜFT' gelistet ist UND das aktuelle Problem dasselbe Themenfeld "
        "berührt, beginne deinen ersten Absatz mit einem kurzen, expliziten Rückbezug "
        "auf das frühere Review (z.B. 'Beim letzten Review war <Konzept> noch offen — "
        "schauen wir, ob es diesmal besser läuft.'). Der Studierende soll spüren, dass "
        "du seinen Weg kennst. Erfinde aber KEINEN Rückbezug, wenn kein gelistetes "
        "Konzept zum aktuellen Problem passt.\n\n"
        "REFERENZ-WISSEN (RAG):\n"
        f"{rag_summary}\n\n"
        "OUTPUT:\n"
        "- Antworte in Markdown.\n"
        f"{output_instructions}"
        "CONTEXT:\n"
        f"{json.dumps(payload, sort_keys=True)}"
    )

def build_follow_up_prompt(
    original_feedback: str,
    prior_messages: list[ThreadMessage],
    question: str,
    rag_summary: str = "",
) -> str:
    history_lines = [
        f"{message.role}: {message.content}" for message in prior_messages
    ]
    history_text = (
        "\n".join(history_lines)
        if history_lines
        else "Keine bisherige Rückfragen-Historie."
    )

    payload = {
        "original_feedback": original_feedback,
        "history": [
            {"role": message.role, "content": message.content}
            for message in prior_messages
        ],
        "question": question,
        "rag_summary": rag_summary,
    }

    return (
        "Du bist ein geduldiger Mentor, der eine Rückfrage zu einem bereits gegebenen "
        "Review-Feedback in einem laufenden Thread beantwortet.\n"
        "RICHTLINIEN:\n"
        "- Antworte sokratisch: stelle Rückfragen, gib KEINE fertige Lösung vor.\n"
        "- Wenn die NEUE FRAGE des Studierenden eine inhaltliche AUSSAGE/Antwort auf deine "
        "vorherige Frage ist: Benenne ZUERST explizit, was an seiner Überlegung richtig ist "
        "(z.B. 'Genau — ...'), oder korrigiere behutsam und konkret, was nicht stimmt, BEVOR "
        "du die nächste Frage stellst. Richtige Überlegungen dürfen nie unkommentiert bleiben — "
        "der Studierende muss wissen, dass er auf dem richtigen Weg ist. Ist die Nachricht "
        "dagegen selbst eine FRAGE, beginne NICHT mit einer Bestätigung wie 'Genau' — "
        "beantworte bzw. behandle sie direkt.\n"
        "- Beziehe dich auf das ursprüngliche Mentor-Feedback und die bisherige Historie.\n"
        "- Nutze das REFERENZ-WISSEN nur als allgemeine Hilfe, nicht als fertige Antwort.\n"
        "- WIEDERHOLE KEINE Frage, die in der BISHERIGEN HISTORIE bereits wortgleich oder "
        "sinngemäß gestellt wurde — auch nicht die Fragen aus der 'Methodischen Checkliste' "
        "im ursprünglichen Feedback. Prüfe die Historie darauf, bevor du antwortest.\n"
        "- Wenn die letzte Antwort des Studierenden Ratlosigkeit zeigt (z.B. 'weiß nicht', "
        "'keine Ahnung', 'keinen Plan') UND du zu diesem Punkt bereits mindestens einmal "
        "nachgefragt hast, wiederhole NICHT dieselbe Frage. Gib stattdessen einen "
        "konkreteren, kleineren Hinweis oder zerlege die Frage in einen leichter "
        "beantwortbaren Teilschritt (z.B. verweise auf eine konkrete Zeile/Funktion aus "
        "den geänderten Dateien) — ohne die vollständige Lösung zu verraten.\n"
        "- AUSNAHME von der Sokratik-Regel: Wenn der Studierende explizit um eine Erklärung "
        "bittet (z.B. 'erklär mir das', 'was bedeutet X', 'kannst du das näher erklären'), "
        "darfst du den allgemeinen Fachbegriff oder das Konzept kurz sachlich erklären "
        "(z.B. was `continue-on-error` in GitHub Actions allgemein bewirkt). Erkläre dabei "
        "NUR das allgemeine Konzept, NICHT die konkrete Lösung für diesen PR — schließe "
        "danach mit einer Rückfrage ab, die den Studierenden zurück zur Anwendung auf seinen "
        "eigenen Code führt.\n\n"
        "URSPRÜNGLICHES MENTOR-FEEDBACK:\n"
        f"{original_feedback}\n\n"
        "BISHERIGE HISTORIE:\n"
        f"{history_text}\n\n"
        "NEUE FRAGE:\n"
        f"{question}\n\n"
        "REFERENZ-WISSEN (RAG):\n"
        f"{rag_summary or 'Kein zusätzlicher Kontext verfügbar.'}\n\n"
        "OUTPUT:\n"
        "- Antworte in Markdown.\n"
        "- Gib keine fertige Lösung vor, stelle stattdessen eine sokratische Rückfrage "
        "ODER einen konkreteren Hinweis, falls die Eskalations-Regel oben greift.\n"
        "CONTEXT:\n"
        f"{json.dumps(payload, sort_keys=True)}"
    )


def _format_file_focus(state: ReviewState) -> str:
    files = [item.get("path", "unknown") for item in state["pr_data"].get("changed_files", [])]
    if not files:
        return "No changed files were provided in the PR metadata."
    return ", ".join(files)


def _format_ci_focus(state: ReviewState) -> str:
    pytest_errors = state["ci_findings"].get("pytest", [])
    mypy_errors = state["ci_findings"].get("mypy", [])
    ruff_errors = state["ci_findings"].get("ruff", [])
    parts = []
    if pytest_errors:
        parts.append(f"{len(pytest_errors)} pytest failure(s)")
    if mypy_errors:
        parts.append(f"{len(mypy_errors)} mypy finding(s)")
    if ruff_errors:
        parts.append(f"{len(ruff_errors)} ruff finding(s)")
    return ", ".join(parts) if parts else "No CI findings were provided."


def _doc_hints(classified_comments: list[ClassifiedCopilotComment]) -> list[str]:
    categories = {comment.category for comment in classified_comments if comment.relevant}
    return [f"- {category}: {DOC_LINKS[category]}" for category in sorted(categories)]


def _rag_citations(rag_context: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    citations: list[str] = []
    for item in rag_context:
        source = str(item.get("source") or "unbekannte Quelle")
        if source in seen:
            continue
        seen.add(source)
        text = str(item.get("text") or "").strip().replace("\n", " ")
        snippet = text[:120]
        citations.append(f'- [{source}]({source}): "{snippet}..."')
    return citations


def build_feedback(
    state: ReviewState,
    decision: ReflectionDecision,
    classified_comments: list[ClassifiedCopilotComment],
    llm_guidance: str,
) -> str:
    """Erstellt ein Review-Feedback im Markdown-Format.

    Zeigt nur Abschnitte mit echtem Inhalt — keine statischen Fülltexte oder
    "nichts gefunden"-Platzhalter, damit das Feedback dicht bleibt.
    """
    sections = [
        "## 🎓 Mentor Feedback",
        f"**Fokus:** `{decision.primary_issue}` | **Schweregrad:** `{decision.severity.upper()}`",
        f"**Betroffene Dateien:** `{_format_file_focus(state)}` | **CI-Status:** `{_format_ci_focus(state)}`",
    ]

    relevant = [comment for comment in classified_comments if comment.relevant]
    if relevant:
        relevant_lines = [
            f"- `{comment.file}:{comment.line or '?'}` [{comment.category.upper()}] {comment.comment}"
            for comment in relevant
        ]
        sections += ["---", "### 🔍 Relevante Anmerkungen", *relevant_lines]

    sections += ["---", "### 🎙️ Mentor-Feedback", llm_guidance.strip()]

    rag_context = state.get("rag_context", [])
    rag_citation_lines = _rag_citations(rag_context)
    if rag_citation_lines:
        sections += ["---", "### 🔗 Verwendete Quellen (RAG)", *rag_citation_lines]

    docs = _doc_hints(classified_comments)
    if docs:
        sections += ["---", "### 📚 Weiterführende Dokumentation", *docs]

    output = "\n\n".join(sections)

    # Artefakt-Sicherung (für Debugging/Protokollierung)
    with open("feedback.md", "w", encoding="utf-8") as f:
        f.write(output)

    return output

def build_verification_prompt(state: ReviewState, guidance: str) -> str:
    rag_data = state.get("rag_context", [])
    payload = {
        "changed_files": state["pr_data"].get("changed_files", []),
        "ci_findings": state["ci_findings"],
        "rag_texte": [d.get("text", "") for d in rag_data],
        "mentor_feedback": guidance,
    }
    return (
        "Du bist ein strenger Faktenprüfer. Prüfe das MENTOR-FEEDBACK auf technische "
        "Behauptungen, die NICHT durch den Diff (changed_files), die CI-Findings oder "
        "die RAG-Texte belegt sind — z.B. erfundenes Tool-Verhalten, behauptete "
        "Seiteneffekte oder Risiken, die nirgends sichtbar sind.\n"
        "REGELN:\n"
        "- Sokratische Fragen und Handlungsvorschläge sind KEINE Behauptungen — nur "
        "Tatsachenaussagen zählen.\n"
        "- 'korrigierte_fassung': das vollständige Feedback mit entfernten oder "
        "vorsichtig umformulierten unbelegten Aussagen. Struktur und alle vier "
        "fettgedruckten Absatz-Labels UNBEDINGT beibehalten. Ändere belegte Teile NICHT.\n"
        "- Wenn alles belegt ist: 'unbelegte_aussagen' als leere Liste, "
        "'korrigierte_fassung' exakt gleich dem Original.\n"
        "- Antworte AUSSCHLIESSLICH mit dem JSON-Objekt, ohne Text davor oder danach.\n"
        "OUTPUT-SCHEMA (JSON): \n"
        "{\"unbelegte_aussagen\": [str], \"korrigierte_fassung\": str}\n"
        f"CONTEXT:\n{json.dumps(payload, sort_keys=True)}"
    )


def verify_mentor_guidance(
    state: ReviewState, guidance: str, llm: BaseLLMClient
) -> tuple[str, int]:
    """Selbstprüfung: zweiter LLM-Pass, der das fertige Feedback gegen Diff/CI/RAG
    prüft und unbelegte Behauptungen entschärft. Schlägt die Prüfung fehl oder
    liefert sie Verdächtiges (z.B. stark verkürzten Text), bleibt das Original
    unverändert — die Prüfung darf nie selbst zum Risiko werden."""
    raw = llm.generate(build_verification_prompt(state, guidance))
    for candidate in (raw, extract_json_snippet(raw)):
        try:
            parsed = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if not isinstance(parsed, dict):
            continue
        claims = parsed.get("unbelegte_aussagen")
        corrected = parsed.get("korrigierte_fassung")
        if not isinstance(claims, list) or not isinstance(corrected, str):
            continue
        corrected = corrected.strip()
        if not claims:
            return guidance, 0
        # Schutz: Eine "Korrektur", die den Text ausweidet, ist keine Korrektur.
        if len(corrected) < 0.3 * len(guidance):
            return guidance, 0
        return corrected, len(claims)
    return guidance, 0


def run_dev_mentor_agent(
    state: ReviewState,
    llm: BaseLLMClient | None = None,
) -> tuple[str, list[ClassifiedCopilotComment]]:
    client = llm or MockLLMClient()
    decision = parse_reflection_decision(state["reflection_decision"])
    classified = classify_copilot_comments(state["copilot_comments"], decision)
    student_id = state["pr_data"].get("metadata", {}).get("author") or "unknown"
    student_profile = summarize_student_profile(student_id)
    llm_guidance = client.generate(
        build_dev_mentor_prompt(state, decision, classified, student_profile)
    )
    if llm_guidance.strip():
        llm_guidance, corrections = verify_mentor_guidance(state, llm_guidance, client)
        if corrections:
            llm_guidance += (
                f"\n\n_🛡️ Selbstprüfung: {corrections} unbelegte Aussage(n) "
                "entfernt oder abgeschwächt._"
            )
    return build_feedback(state, decision, classified, llm_guidance), classified


def dev_mentor_agent_node(llm: BaseLLMClient | None = None):
    def node(state: ReviewState) -> ReviewState:
        feedback, classified_comments = run_dev_mentor_agent(state, llm=llm)
        updated = deepcopy(state)
        updated["mentor_feedback"] = feedback
        updated["copilot_comments"] = [
            comment.model_dump(exclude_none=True) for comment in classified_comments
        ]
        return cast(ReviewState, updated)

    return node


def build_praise_prompt(state: ReviewState) -> str:
    payload = {
        "changed_files": state["pr_data"].get("changed_files", []),
        "ci_findings": state["ci_findings"],
    }
    return (
        "Du bist ein Mentor. Dieser Pull Request wurde bereits geprüft: CI ist grün und es "
        "wurden KEINE Probleme gefunden — es gibt nichts zu beanstanden.\n"
        "AUFGABE: Erkläre in 3-5 Sätzen, was an diesem PR konkret gut gelöst ist, damit der "
        "Studierende sein gutes Vorgehen bewusst wiederholen kann (Lernen am positiven Beispiel).\n"
        "REGELN:\n"
        "- Beziehe dich NUR auf das, was in den geänderten Dateien tatsächlich sichtbar ist "
        "(z.B. klare Benennung, sinnvolle Doku, saubere kleine Änderung) — erfinde nichts.\n"
        "- ERFINDE keine Probleme und keine künstlichen 'Verbesserungsvorschläge' — der PR "
        "ist in Ordnung, und das darf so stehen bleiben.\n"
        "- Antworte in Markdown, ohne eigene Überschrift (die ergänzt das System).\n"
        f"CONTEXT:\n{json.dumps(payload, sort_keys=True)}"
    )


def run_praise_agent(state: ReviewState, llm: BaseLLMClient | None = None) -> str:
    """Lernen am positiven Beispiel: Wenn Reflection 'end' entscheidet (sauberer PR),
    bekommt der Studierende eine kurze Würdigung statt eines leeren Threads."""
    client = llm or MockLLMClient()
    guidance = client.generate(build_praise_prompt(state)).strip()
    if not guidance:
        guidance = (
            "Alle CI-Checks sind grün und die Änderungen sind sauber umgesetzt — "
            "hier gibt es nichts zu beanstanden. Weiter so!"
        )
    return "\n\n".join(
        [
            "## ✅ Review ohne Beanstandungen",
            f"**Betroffene Dateien:** `{_format_file_focus(state)}` | "
            f"**CI-Status:** `{_format_ci_focus(state)}`",
            guidance,
        ]
    )


def praise_agent_node(llm: BaseLLMClient | None = None):
    def node(state: ReviewState) -> ReviewState:
        updated = deepcopy(state)
        updated["mentor_feedback"] = run_praise_agent(state, llm=llm)
        return cast(ReviewState, updated)

    return node
