from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable

from codementor.rag.embeddings import get_embedding_function
from codementor.rag.sources import fetch_url_text


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


def index_documents(
    urls: Iterable[str],
    persist_dir: str,
    embedding_function,
    refresh: bool = False,
) -> int:
    collection = _get_collection(persist_dir, embedding_function)
    if refresh:
        existing = collection.get()
        ids = existing.get("ids", [])
        if ids:
            collection.delete(ids=ids)

    added = 0
    for url in urls:
        text = fetch_url_text(url)
        for idx, chunk in enumerate(_chunk_text(text)):
            chunk_id = _make_chunk_id(url, idx, chunk)
            collection.add(
                ids=[chunk_id],
                documents=[chunk],
                metadatas=[{"source": url, "chunk_index": idx}],
            )
            added += 1
    return added


def index_documents_with_config(
    urls: Iterable[str],
    persist_dir: str,
    config,
    refresh: bool = False,
) -> int:
    embedding_function = get_embedding_function(config)
    return index_documents(urls, persist_dir, embedding_function, refresh=refresh)
