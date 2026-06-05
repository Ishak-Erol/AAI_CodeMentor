from __future__ import annotations

from codementor.rag.embeddings import SimpleHashEmbeddingFunction
from codementor.rag.retriever import retrieve_context


def test_simple_hash_embedding_function_is_deterministic() -> None:
    fn = SimpleHashEmbeddingFunction(dimension=16)
    first = fn(["pytest failure handling"])[0]
    second = fn(["pytest failure handling"])[0]

    assert first == second


def test_retrieve_context_returns_results(tmp_path) -> None:
    import chromadb

    client = chromadb.PersistentClient(path=str(tmp_path))
    collection = client.get_or_create_collection(
        name="codementor-docs",
        embedding_function=SimpleHashEmbeddingFunction(),
    )
    collection.add(
        ids=["doc-1"],
        documents=["pytest fixtures help organize tests"],
        metadatas=[{"source": "doc"}],
    )

    results = retrieve_context("pytest fixtures", str(tmp_path), top_k=1)

    assert results
    assert "pytest" in results[0]["text"]
