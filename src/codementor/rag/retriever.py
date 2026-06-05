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

    return " ".join(part for part in parts if part).strip()


def retrieve_context(
    query: str,
    persist_dir: str,
    top_k: int,
    embedding_function=None,
) -> list[dict[str, Any]]:
    if not query:
        return []
    embed_fn = embedding_function or SimpleHashEmbeddingFunction()
    collection = _get_collection(persist_dir, embed_fn)
    results = collection.query(query_texts=[query], n_results=top_k)
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    context: list[dict[str, Any]] = []
    for doc, meta in zip(documents, metadatas, strict=False):
        context.append(
            {
                "source": meta.get("source") if isinstance(meta, dict) else None,
                "text": doc,
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
        index_documents(urls, config.rag_path, embedding_function, refresh=True)
    else:
        collection = _get_collection(config.rag_path, embedding_function)
        if collection.count() == 0:
            index_documents(urls, config.rag_path, embedding_function, refresh=False)

    query = build_query(pr_data, ci_findings, copilot_comments)
    return retrieve_context(
        query,
        config.rag_path,
        config.rag_top_k,
        embedding_function=embedding_function,
    )
