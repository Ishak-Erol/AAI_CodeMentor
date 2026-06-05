from __future__ import annotations

import json
from abc import ABC, abstractmethod
import logging
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
        timeout: float = 30.0,
    ) -> None:
        if not api_key:
            raise LLMClientError("API_KEY is required for live LLM usage.")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

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
            "temperature": 0.2,
        }
        logger.info("LLM request %s", url)
        try:
            response = httpx.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Accept": "application/json",
                },
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise LLMClientError("Network error while calling LLM API.") from exc

        if response.status_code >= 400:
            raise LLMClientError(
                f"LLM API request failed with status {response.status_code}."
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMClientError("LLM API returned invalid JSON.") from exc

        return _extract_message_content(data)


def _extract_message_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMClientError("LLM response missing choices.")
    message = choices[0].get("message", {})
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise LLMClientError("LLM response missing content.")
    return content


class MockLLMClient(BaseLLMClient):
    """Deterministic offline LLM client for Sprint 1 tests and demos."""

    def generate(self, prompt: str) -> str:
        lowered = prompt.lower()
        if "agent: reflection" in lowered:
            return self._reflection_response(prompt)
        if "agent: dev_mentor" in lowered:
            return self._mentor_response()
        if "agent: learning" in lowered:
            return self._learning_response(lowered)
        return ""

    def _reflection_response(self, prompt: str) -> str:
        context = self._extract_context(prompt)
        ci_findings = context.get("ci_findings", {})
        copilot_comment_count = int(context.get("copilot_comment_count", 0) or 0)

        if ci_findings.get("pytest"):
            response = {
                "primary_issue": "testing",
                "severity": "high",
                "needs_copilot_analysis": True,
                "next_agent": "dev_mentor",
            }
        elif ci_findings.get("mypy"):
            response = {
                "primary_issue": "typing",
                "severity": "medium",
                "needs_copilot_analysis": True,
                "next_agent": "dev_mentor",
            }
        elif ci_findings.get("ruff"):
            response = {
                "primary_issue": "code_quality",
                "severity": "medium",
                "needs_copilot_analysis": copilot_comment_count > 0,
                "next_agent": "dev_mentor",
            }
        elif copilot_comment_count > 0:
            response = {
                "primary_issue": "copilot_review",
                "severity": "medium",
                "needs_copilot_analysis": True,
                "next_agent": "dev_mentor",
            }
        else:
            response = {
                "primary_issue": "code_quality",
                "severity": "medium",
                "needs_copilot_analysis": False,
                "next_agent": "dev_mentor",
            }
        return json.dumps(response)

    def _extract_context(self, prompt: str) -> dict:
        marker = "CONTEXT:\n"
        if marker not in prompt:
            return {}
        try:
            return json.loads(prompt.split(marker, maxsplit=1)[1])
        except json.JSONDecodeError:
            return {}

    def _mentor_response(self) -> str:
        return (
            "Use questions that guide the developer from the failing CI signal "
            "back to the smallest missing safety net. Avoid giving a full patch."
        )

    def _learning_response(self, prompt: str) -> str:
        points = [
            {
                "concept": "pytest fixtures",
                "difficulty": "medium",
                "reason": (
                    "Relevant because the PR needs a shared setup around parser "
                    "inputs and regression cases."
                ),
            },
            {
                "concept": "mypy Optional handling",
                "difficulty": "medium",
                "reason": (
                    "Relevant because CI reports a path where payload.get can "
                    "return None before len is called."
                ),
            },
        ]
        if "copilot" in prompt or "review_parser.py" in prompt:
            points.append(
                {
                    "concept": "triaging Copilot review comments",
                    "difficulty": "easy",
                    "reason": (
                        "Relevant because review comments need to be grouped by "
                        "risk, testing, typing, and readability before action."
                    ),
                }
            )
        return json.dumps(points)
