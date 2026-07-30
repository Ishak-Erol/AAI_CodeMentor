from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx


class BaseLLMClient(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Generate an LLM response for a prompt."""


logger = logging.getLogger(__name__)


class LLMClientError(RuntimeError):
    """Raised when the LLM provider returns an error."""


class OpenAICompatibleLLMClient(BaseLLMClient):
    def __init__(
        self,
        api_key: str | None,
        base_url: str,
        model: str,
        timeout: float = 60.0,
        temperature: float = 0.2,
    ) -> None:
        if not api_key:
            raise LLMClientError("API_KEY is required for live LLM usage.")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._temperature = temperature

    def generate(self, prompt: str) -> str:
        url = f"{self._base_url}/chat/completions"
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": (
                    "Du bist CodeMentor, ein deutschsprachiger didaktischer Code-Review-Assistent. "
                    "Antworte immer auf Deutsch. "
                    "Gib lernorientiertes Feedback. "
                    "Stelle bevorzugt sokratische Rückfragen statt direkt vollständige Lösungen vorzugeben."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": self._temperature,
        }
        logger.info("LLM request %s", url)
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }
        # Retries bei transienten Fehlern (5xx/Netz) — die AcademicCloud-API
        # antwortet gelegentlich sporadisch mit 500. Das LLM ist (anders als RAG)
        # nicht optional: Schlägt auch der letzte Versuch fehl, gibt es einen
        # sauberen LLMClientError, den die UI als Fehlermeldung rendert.
        last_error: str = "unknown"
        for attempt in (1, 2, 3):
            if attempt > 1:
                time.sleep(1.5 * (attempt - 1))
            try:
                response = httpx.post(
                    url, json=payload, headers=headers, timeout=self._timeout
                )
            except httpx.HTTPError as exc:
                last_error = f"Network error while calling LLM API ({exc})."
                logger.warning("LLM-Request fehlgeschlagen (Versuch %d): %s", attempt, exc)
                continue

            if response.status_code >= 500:
                last_error = (
                    f"LLM API request failed with status {response.status_code}."
                )
                logger.warning("LLM-API %d (Versuch %d)", response.status_code, attempt)
                continue
            if response.status_code >= 400:
                raise LLMClientError(
                    f"LLM API request failed with status {response.status_code}."
                )

            try:
                data = response.json()
            except ValueError as exc:
                raise LLMClientError("LLM API returned invalid JSON.") from exc

            return _extract_message_content(data)

        raise LLMClientError(
            f"LLM API nicht erreichbar (3 Versuche): {last_error} "
            "Vermutlich eine vorübergehende Störung der AcademicCloud — "
            "bitte in ein paar Minuten erneut versuchen."
        )


def _extract_message_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMClientError("LLM response missing choices.")
    message = choices[0].get("message", {})
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise LLMClientError("LLM response missing content.")
    return content


class NullLLMClient(BaseLLMClient):
    """Antwortet auf jeden Prompt mit einem leeren String.

    Wird nur dort eingesetzt, wo kein API-Key konfiguriert ist. Jeder Agent
    fällt bei leerer Antwort auf sein deterministisches Fallback-Verhalten
    zurück (siehe `parse_reflection_decision`), sodass die Anwendung ohne
    Key startet — aber ohne echtes, LLM-gestütztes Feedback.

    Reviews mit echtem Mehrwert brauchen `API_KEY`.
    """

    def generate(self, prompt: str) -> str:
        return ""
