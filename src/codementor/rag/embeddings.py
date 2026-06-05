from __future__ import annotations

import hashlib
import logging
import math
from typing import Any

import httpx

from codementor.config import AppConfig


logger = logging.getLogger(__name__)


class SimpleHashEmbeddingFunction:
    def __init__(self, dimension: int = 256) -> None:
        self.dimension = dimension

    def name(self) -> str:
        return "simple-hash"

    def is_legacy(self) -> bool:
        return False

    def __call__(self, input: list[str]) -> list[list[float]]:
        return self._embed(input)

    def embed_documents(self, input: list[str]) -> list[list[float]]:
        return self._embed(input)

    def embed_query(self, input: list[str]) -> list[list[float]]:
        return self._embed(input)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dimension
            for token in text.lower().split():
                digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
                idx = int(digest, 16) % self.dimension
                vector[idx] += 1.0
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            embeddings.append([value / norm for value in vector])
        return embeddings


class OpenAICompatibleEmbeddingFunction:
    def __init__(
        self,
        api_key: str | None,
        base_url: str,
        model: str,
        timeout: float = 30.0,
    ) -> None:
        if not api_key:
            raise RuntimeError("API_KEY is required for embeddings.")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def name(self) -> str:
        return f"openai-compatible-{self._model}"

    def is_legacy(self) -> bool:
        return False

    def __call__(self, input: list[str]) -> list[list[float]]:
        return self._embed(input)

    def embed_documents(self, input: list[str]) -> list[list[float]]:
        return self._embed(input)

    def embed_query(self, input: list[str]) -> list[list[float]]:
        return self._embed(input)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        texts = [text[:1000] for text in texts]
        url = f"{self._base_url}/embeddings"
        logger.info("Embedding request %s", url)
        payload = {
            "input": texts,
            "model": self._model,
            "encoding_format": "float",
        }
        response = httpx.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Accept": "application/json",
            },
            timeout=self._timeout,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Embedding API request failed with status {response.status_code}: "
                f"{response.text}"
            )
        data = response.json()
        return _extract_embeddings(data)

def _extract_embeddings(payload: dict[str, Any]) -> list[list[float]]:
    items = payload.get("data")
    if not isinstance(items, list):
        raise RuntimeError("Embedding response missing data.")
    embeddings: list[list[float]] = []
    for item in items:
        vector = item.get("embedding") if isinstance(item, dict) else None
        if not isinstance(vector, list):
            raise RuntimeError("Embedding response missing vector.")
        embeddings.append([float(value) for value in vector])
    return embeddings


def get_embedding_function(config: AppConfig):
    if config.rag_use_api_embeddings:
        return OpenAICompatibleEmbeddingFunction(
            api_key=config.llm_api_key,
            base_url=config.llm_base_url,
            model=config.embed_model,
        )
    return SimpleHashEmbeddingFunction()
