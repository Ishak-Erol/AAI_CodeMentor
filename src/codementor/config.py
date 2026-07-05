from __future__ import annotations

from dataclasses import dataclass
import os


DEFAULT_COPILOT_ALLOWLIST = ["copilot", "github-copilot[bot]"]
DEFAULT_API_BASE_URL = "https://api.github.com"
DEFAULT_ARTIFACT_NAME = "codementor-analysis"
DEFAULT_RAG_PATH = ".codementor/rag"
DEFAULT_RAG_TOP_K = 4
# Relevanz-Schwelle (Chroma-L2-Distanz): Treffer oberhalb werden verworfen —
# lieber ehrlich "keine passende Doku" als eine unpassende Quelle zitieren.
# Empirisch gegen den echten Index mit E5-API-Embeddings kalibriert:
# relevante Queries lagen bei 0.17-0.25, irrelevante bei 0.36-0.43.
# Gilt NUR für API-Embeddings — die Hash-Fallback-Embeddings haben eine andere
# Distanzskala (relevant ~0.85), dort bleibt der Filter aus (0 = deaktiviert).
DEFAULT_RAG_MAX_DISTANCE = 0.32
# Depth-1-Crawl: Startseite plus max. so viele intern verlinkte Unterseiten
# derselben Doku-Sektion pro Quelle.
DEFAULT_RAG_MAX_PAGES = 15
DEFAULT_LLM_BASE_URL = "https://chat-ai.academiccloud.de/v1"
# devstral-2: auf der AcademicCloud für "Coding, agentic tasks" ausgewiesen —
# hält JSON-Schemata deutlich zuverlässiger ein als das frühere 8B-Modell und
# erklärt Konzepte fachlich korrekt (beides verifiziert gegen die Live-API).
DEFAULT_LLM_MODEL = "devstral-2-123b-instruct-2512"
DEFAULT_LLM_TEMPERATURE = 0.2
DEFAULT_EMBED_MODEL = "multilingual-e5-large-instruct"
DEFAULT_DB_PATH = "codementor.db"


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
    rag_max_distance: float
    rag_max_pages: int
    llm_api_key: str | None
    llm_base_url: str
    llm_model: str
    llm_temperature: float
    embed_model: str
    llm_enabled: bool
    rag_use_api_embeddings: bool
    db_path: str


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
    # LLM automatisch aktiv, sobald ein API-Key gesetzt ist — sonst startet die UI
    # still mit dem Mock-Client und liefert leere Mentor-Antworten. Ein explizit
    # gesetztes CODEMENTOR_LLM_ENABLED (auch "0"/"false") hat weiterhin Vorrang.
    llm_enabled_raw = os.getenv("CODEMENTOR_LLM_ENABLED")
    llm_enabled = (
        _parse_bool(llm_enabled_raw) if llm_enabled_raw is not None else bool(api_key)
    )
    rag_use_api_embeddings = _parse_bool(
        os.getenv("CODEMENTOR_RAG_USE_API_EMBEDDINGS")
    ) or bool(api_key)
    # Kalibrierte Schwelle nur für API-Embeddings; Hash-Fallback: Filter aus.
    default_max_distance = (
        DEFAULT_RAG_MAX_DISTANCE if rag_use_api_embeddings else 0.0
    )
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
        rag_max_distance=float(
            os.getenv("CODEMENTOR_RAG_MAX_DISTANCE", str(default_max_distance))
        ),
        rag_max_pages=int(
            os.getenv("CODEMENTOR_RAG_MAX_PAGES", str(DEFAULT_RAG_MAX_PAGES))
        ),
        llm_api_key=api_key,
        llm_base_url=os.getenv("CODEMENTOR_LLM_BASE_URL", DEFAULT_LLM_BASE_URL),
        llm_model=os.getenv("CODEMENTOR_LLM_MODEL", DEFAULT_LLM_MODEL),
        llm_temperature=float(
            os.getenv("CODEMENTOR_LLM_TEMPERATURE", str(DEFAULT_LLM_TEMPERATURE))
        ),
        embed_model=os.getenv("CODEMENTOR_EMBED_MODEL", DEFAULT_EMBED_MODEL),
        llm_enabled=llm_enabled,
        rag_use_api_embeddings=rag_use_api_embeddings,
        db_path=os.getenv("CODEMENTOR_DB_PATH", DEFAULT_DB_PATH),
    )
