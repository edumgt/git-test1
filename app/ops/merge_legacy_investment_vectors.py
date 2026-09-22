"""Migrate only legacy-only investment RAG chunks into the shared corpus."""

from __future__ import annotations

from app.core.database import SessionLocal
from app.models.document_chunk import DocumentChunk
from app.services.embedder import EmbeddingService
from app.services.vector_store import VectorStore
from app.core.config import settings


LEGACY_COLLECTION = "investment_docs"
# All other legacy source files were already imported as their newer, more
# finely chunked counterparts (03/04/05/06/07/10-1/10-2/10-3/11/voca).
LEGACY_ONLY_SOURCES = {"10.md"}


def main() -> None:
    session = SessionLocal()
    try:
        store = VectorStore()
        collections = {item.name for item in store.client.get_collections().collections}
        if LEGACY_COLLECTION not in collections:
            print(f"{LEGACY_COLLECTION} already absent; nothing to migrate")
            return

        points, _ = store.client.scroll(
            collection_name=LEGACY_COLLECTION,
            limit=1_000,
            with_payload=True,
            with_vectors=False,
        )
        selected = [point for point in points if point.payload.get("source_doc") in LEGACY_ONLY_SOURCES]
        chunks = [
            {
                "chunk_id": f"investment-legacy-10-{point.payload.get('chunk_index', index)}",
                "document_id": "investment-legacy-10",
                "title": "investment-analysis · 10.md (legacy reference)",
                "content": str(point.payload.get("text", "")),
                "chunk_index": int(point.payload.get("chunk_index", index)),
                "domain": "general",
                "metadata": {"migrated_from": LEGACY_COLLECTION, "source_doc": "10.md"},
            }
            for index, point in enumerate(selected)
            if point.payload.get("text")
        ]
        if not chunks:
            raise RuntimeError("legacy-only source chunks were not found")

        new_chunks = [chunk for chunk in chunks if not session.query(DocumentChunk.id).filter_by(chunk_id=chunk["chunk_id"]).first()]
        if new_chunks:
            vectors = EmbeddingService(settings.embedding_model).embed_texts([chunk["content"] for chunk in new_chunks])
            store.upsert_chunks(new_chunks, vectors)
            session.add_all([DocumentChunk(**{key: value for key, value in chunk.items() if key != "metadata"}) for chunk in new_chunks])
            session.commit()

        expected = len(chunks)
        actual = session.query(DocumentChunk).filter(DocumentChunk.document_id == "investment-legacy-10").count()
        if actual != expected:
            raise RuntimeError(f"migration verification failed: expected={expected}, stored={actual}")

        # Keep the legacy collection as a rollback-only backup.  Normal user
        # endpoints already use domain_docs; retirement can be done later
        # after an explicit retention decision.
        total = store.client.count(collection_name=store.collection_name, exact=True).count
        print(f"completed: migrated={len(new_chunks)}, retained={expected}, domain_docs={total}, backup={LEGACY_COLLECTION}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
