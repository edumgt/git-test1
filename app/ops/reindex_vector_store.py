"""Rebuild the Qdrant index from the authoritative PostgreSQL RAG chunks.

This deliberately never changes ``document_chunks``.  It only recreates the
configured Qdrant collection, making it safe to use when embeddings or the
vector index need to be regenerated.
"""

from __future__ import annotations

from app.core.database import SessionLocal
from app.models.document_chunk import DocumentChunk
from app.services.embedder import EmbeddingService
from app.services.vector_store import VectorStore
from app.core.config import settings


BATCH_SIZE = 64


def main() -> None:
    session = SessionLocal()
    try:
        total = session.query(DocumentChunk).count()
        if not total:
            raise RuntimeError("document_chunks에 재색인할 원본 청크가 없습니다.")

        vector_store = VectorStore()
        collection = vector_store.collection_name
        existing = {item.name for item in vector_store.client.get_collections().collections}
        if collection in existing:
            vector_store.client.delete_collection(collection_name=collection)
        vector_store._ensure_collection()

        embedder = EmbeddingService(settings.embedding_model)
        processed = 0
        for offset in range(0, total, BATCH_SIZE):
            rows = (
                session.query(DocumentChunk)
                .order_by(DocumentChunk.id)
                .offset(offset)
                .limit(BATCH_SIZE)
                .all()
            )
            chunks = [
                {
                    "chunk_id": row.chunk_id,
                    "document_id": row.document_id,
                    "title": row.title,
                    "content": row.content,
                    "chunk_index": row.chunk_index,
                    "domain": row.domain,
                }
                for row in rows
            ]
            vector_store.upsert_chunks(chunks, embedder.embed_texts([row["content"] for row in chunks]))
            processed += len(chunks)
            print(f"reindexed {processed}/{total} chunks", flush=True)

        result = vector_store.client.count(collection_name=collection, exact=True)
        if result.count != total:
            raise RuntimeError(f"재색인 검증 실패: PostgreSQL={total}, Qdrant={result.count}")
        print(f"completed: PostgreSQL={total}, Qdrant={result.count}, collection={collection}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
