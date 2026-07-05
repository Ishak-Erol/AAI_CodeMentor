from __future__ import annotations

from dataclasses import dataclass
import hashlib
import logging
from typing import Iterable

from codementor.rag.embeddings import get_embedding_function
from codementor.rag.sources import crawl_source


logger = logging.getLogger(__name__)

DEFAULT_MAX_PAGES_PER_SOURCE = 15
# Embedding-APIs kappen große Payloads (Connection-Reset bei Seiten mit 100+
# Chunks in einem Request) — deshalb in kleinen Batches einfügen.
EMBED_BATCH_SIZE = 32


@dataclass(frozen=True)
class DocumentChunk:
    source: str
    text: str


def _chunk_text(text: str, max_chars: int = 500) -> list[str]:
    if not text:
        return []
    paragraphs = [part.strip() for part in text.split("\n") if part.strip()]
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for part in paragraphs:
        if size + len(part) + 1 > max_chars and current:
            chunks.append(" ".join(current))
            current = [part]
            size = len(part)
        else:
            current.append(part)
            size += len(part) + 1
    if current:
        chunks.append(" ".join(current))
    return chunks


def _make_chunk_id(source: str, index: int, text: str) -> str:
    payload = f"{source}:{index}:{text}".encode("utf-8")
    return hashlib.sha1(payload).hexdigest()


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


def _reset_collection(persist_dir: str, embedding_function):
    """Deletes and recreates the collection rather than just clearing its
    documents. A collection's embedding dimension is fixed at creation time —
    if the embedding function changed since then (e.g. switching from the
    256-dim hash fallback to a real 1024-dim API model), clearing documents
    alone leaves a stale dimension constraint and the next `.add()` fails with
    'expecting embedding with dimension of X, got Y'."""
    import chromadb

    client = chromadb.PersistentClient(path=persist_dir)
    try:
        client.delete_collection(name="codementor-docs")
    except Exception:
        pass
    return client.get_or_create_collection(
        name="codementor-docs",
        embedding_function=embedding_function,
    )


def index_documents(
    urls: Iterable[str],
    persist_dir: str,
    embedding_function,
    refresh: bool = False,
    max_pages_per_source: int = DEFAULT_MAX_PAGES_PER_SOURCE,
) -> int:
    collection = (
        _reset_collection(persist_dir, embedding_function)
        if refresh
        else _get_collection(persist_dir, embedding_function)
    )

    added = 0
    for url in urls:
        pages = crawl_source(url, max_pages=max_pages_per_source)
        for page_url, text in pages:
            chunks = _chunk_text(text)
            if not chunks:
                continue
            # `source` ist die exakte Seiten-URL, damit Zitate direkt auf die
            # richtige Unterseite verlinken.
            for start in range(0, len(chunks), EMBED_BATCH_SIZE):
                batch = chunks[start : start + EMBED_BATCH_SIZE]
                try:
                    collection.add(
                        ids=[
                            _make_chunk_id(page_url, start + idx, chunk)
                            for idx, chunk in enumerate(batch)
                        ],
                        documents=batch,
                        metadatas=[
                            {
                                "source": page_url,
                                "chunk_index": start + idx,
                                "root_source": url,
                            }
                            for idx in range(len(batch))
                        ],
                    )
                    added += len(batch)
                except Exception as exc:  # noqa: BLE001 — eine Seite darf ausfallen
                    logger.warning(
                        "Batch für %s übersprungen (%s)", page_url, exc
                    )
        logger.info("Indexed %s (%d Seite(n))", url, len(pages))
    return added


def index_documents_with_config(
    urls: Iterable[str],
    persist_dir: str,
    config,
    refresh: bool = False,
) -> int:
    embedding_function = get_embedding_function(config)
    return index_documents(urls, persist_dir, embedding_function, refresh=refresh)
