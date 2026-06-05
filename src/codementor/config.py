from __future__ import annotations

from dataclasses import dataclass
import os


DEFAULT_COPILOT_ALLOWLIST = ["copilot", "github-copilot[bot]"]
DEFAULT_API_BASE_URL = "https://api.github.com"
DEFAULT_ARTIFACT_NAME = "codementor-analysis"
DEFAULT_RAG_PATH = ".codementor/rag"
DEFAULT_RAG_TOP_K = 4
DEFAULT_LLM_BASE_URL = "https://chat-ai.academiccloud.de/v1"
DEFAULT_LLM_MODEL = "meta-llama-3.1-8b-instruct"
DEFAULT_EMBED_MODEL = "multilingual-e5-large-instruct"


@dataclass(frozen=True)
class AppConfig:
    github_token: str | None
    github_api_base_url: str
    copilot_author_allowlist: list[str]
    artifact_name: str
    workflow_name: str | None
    rag_enabled: bool
    rag_path: str
    rag_doc_urls: list[str]
    rag_top_k: int
    llm_api_key: str | None
    llm_base_url: str
    llm_model: str
    embed_model: str
    llm_enabled: bool
    rag_use_api_embeddings: bool


def _parse_allowlist(raw_value: str | None) -> list[str]:
    if not raw_value:
        return DEFAULT_COPILOT_ALLOWLIST.copy()
    parts = [item.strip().lower() for item in raw_value.split(",")]
    return [item for item in parts if item]


def _parse_bool(raw_value: str | None) -> bool:
    if not raw_value:
        return False
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_urls(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    parts = [item.strip() for item in raw_value.split(",")]
    return [item for item in parts if item]


def get_config() -> AppConfig:
    api_key = os.getenv("API_KEY")
    return AppConfig(
        github_token=os.getenv("GITHUB_TOKEN"),
        github_api_base_url=os.getenv("GITHUB_API_BASE_URL", DEFAULT_API_BASE_URL),
        copilot_author_allowlist=_parse_allowlist(
            os.getenv("COPILOT_AUTHOR_ALLOWLIST")
        ),
        artifact_name=os.getenv("CODEMENTOR_ARTIFACT_NAME", DEFAULT_ARTIFACT_NAME),
        workflow_name=os.getenv("CODEMENTOR_WORKFLOW_NAME"),
        rag_enabled=_parse_bool(os.getenv("CODEMENTOR_RAG_ENABLED")),
        rag_path=os.getenv("CODEMENTOR_RAG_PATH", DEFAULT_RAG_PATH),
        rag_doc_urls=_parse_urls(os.getenv("CODEMENTOR_DOC_URLS")),
        rag_top_k=int(os.getenv("CODEMENTOR_RAG_TOP_K", str(DEFAULT_RAG_TOP_K))),
        llm_api_key=api_key,
        llm_base_url=os.getenv("CODEMENTOR_LLM_BASE_URL", DEFAULT_LLM_BASE_URL),
        llm_model=os.getenv("CODEMENTOR_LLM_MODEL", DEFAULT_LLM_MODEL),
        embed_model=os.getenv("CODEMENTOR_EMBED_MODEL", DEFAULT_EMBED_MODEL),
        llm_enabled=_parse_bool(os.getenv("CODEMENTOR_LLM_ENABLED")),
        rag_use_api_embeddings=_parse_bool(
            os.getenv("CODEMENTOR_RAG_USE_API_EMBEDDINGS")
        )
        or bool(api_key),
    )
