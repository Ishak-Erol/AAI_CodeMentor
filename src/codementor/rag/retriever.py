from __future__ import annotations

from typing import Any, Iterable

from codementor.config import AppConfig
from codementor.rag.embeddings import get_embedding_function, SimpleHashEmbeddingFunction
from codementor.rag.indexer import index_documents
from codementor.rag.sources import ensure_doc_urls


def _get_collection(persist_dir: str, embedding_function):
    try:
        import chromadb
    except ImportError as exc:
        raise RuntimeError("ChromaDB is required for RAG support.") from exc

    client = chromadb.PersistentClient(path=persist_dir)
    return client.get_or_create_collection(
        name="codementor-docs",
        embedding_function=embedding_function,
    )


_MAX_DIFF_QUERY_CHARS = 500


def _diff_keyword_snippets(pr_data: dict[str, Any]) -> list[str]:
    """Extracts concrete added-line snippets from the PR diff (capped in length).

    Generic PR titles/descriptions (e.g. "Demo/comment") or empty CI findings/
    comments leave the RAG query with nothing specific to search for. The added
    diff lines usually contain the actual technical terms/syntax (e.g. a changed
    GitHub Actions key like `continue-on-error`) that real documentation could
    ground an explanation in — so pull those in directly, capped so a large diff
    doesn't dilute the query with too much noise.
    """
    snippets: list[str] = []
    total_len = 0
    for changed_file in pr_data.get("changed_files", []):
        diff_text = str(changed_file.get("diff") or "")
        for line in diff_text.splitlines():
            if not line.startswith("+") or line.startswith("+++"):
                continue
            cleaned = line[1:].strip()
            if not cleaned:
                continue
            snippets.append(cleaned)
            total_len += len(cleaned)
            if total_len > _MAX_DIFF_QUERY_CHARS:
                return snippets
    return snippets


def build_query(
    pr_data: dict[str, Any],
    ci_findings: dict[str, Any],
    copilot_comments: list[dict[str, Any]],
) -> str:
    parts: list[str] = []
    metadata = pr_data.get("metadata", {})
    if metadata.get("title"):
        parts.append(str(metadata.get("title")))
    if metadata.get("description"):
        parts.append(str(metadata.get("description")))

    for tool, findings in ci_findings.items():
        if not findings:
            continue
        parts.append(f"{tool} findings")
        for item in findings[:5]:
            message = item.get("message") or item.get("comment") or ""
            parts.append(str(message))

    for comment in copilot_comments[:5]:
        parts.append(str(comment.get("comment") or ""))

    parts.extend(_diff_keyword_snippets(pr_data))

    return " ".join(part for part in parts if part).strip()


def retrieve_context(
    query: str,
    persist_dir: str,
    top_k: int,
    embedding_function=None,
    max_distance: float | None = None,
) -> list[dict[str, Any]]:
    """Semantische Suche mit optionaler Relevanz-Schwelle: Treffer, deren
    Distanz über `max_distance` liegt, werden verworfen — lieber ehrlich keine
    Quelle zurückgeben als eine thematisch unpassende als Beleg auszuweisen.
    `max_distance` <= 0 oder None deaktiviert den Filter."""
    if not query:
        return []
    embed_fn = embedding_function or SimpleHashEmbeddingFunction()
    collection = _get_collection(persist_dir, embed_fn)
    results = collection.query(query_texts=[query], n_results=top_k)
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = (results.get("distances") or [[]])[0]
    if len(distances) < len(documents):
        distances = list(distances) + [None] * (len(documents) - len(distances))
    context: list[dict[str, Any]] = []
    for doc, meta, distance in zip(documents, metadatas, distances, strict=False):
        if (
            max_distance is not None
            and max_distance > 0
            and distance is not None
            and distance > max_distance
        ):
            continue
        context.append(
            {
                "source": meta.get("source") if isinstance(meta, dict) else None,
                "text": doc,
                "distance": distance,
            }
        )
    return context


def get_rag_context(
    pr_data: dict[str, Any],
    ci_findings: dict[str, Any],
    copilot_comments: list[dict[str, Any]],
    config: AppConfig,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    embedding_function = get_embedding_function(config)
    urls = ensure_doc_urls(config.rag_doc_urls)
    if refresh:
        index_documents(
            urls,
            config.rag_path,
            embedding_function,
            refresh=True,
            max_pages_per_source=config.rag_max_pages,
        )
    else:
        collection = _get_collection(config.rag_path, embedding_function)
        if collection.count() == 0:
            index_documents(
                urls,
                config.rag_path,
                embedding_function,
                refresh=False,
                max_pages_per_source=config.rag_max_pages,
            )

    query = build_query(pr_data, ci_findings, copilot_comments)
    return retrieve_context(
        query,
        config.rag_path,
        config.rag_top_k,
        embedding_function=embedding_function,
        max_distance=config.rag_max_distance,
    )
