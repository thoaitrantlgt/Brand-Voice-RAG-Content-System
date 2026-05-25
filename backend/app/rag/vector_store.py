"""
rag/vector_store.py — ChromaDB Vector Store Implementation
SRP: Chỉ chịu trách nhiệm persist và query embeddings trong ChromaDB.
LSP: Implement đúng IVectorStore — có thể swap sang Qdrant/Pinecone sau này.
"""
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import Settings
from app.core.exceptions import AppBaseException
from app.core.interfaces import IVectorStore
from app.core.logging import logger
from app.rag.embeddings_factory import EmbeddingsFactory


class ChromaVectorStore(IVectorStore):
    """
    ChromaDB implementation của IVectorStore.
    Dữ liệu được persist xuống disk tại CHROMA_PERSIST_DIR.
    """

    def __init__(self, settings: Settings) -> None:
        """DIP: Nhận Settings và tạo ChromaDB client nội bộ."""
        self._settings = settings
        self._collection = self._init_collection()

    def _init_collection(self):
        """Khởi tạo ChromaDB persistent client và collection."""
        persist_dir = Path(self._settings.CHROMA_PERSIST_DIR)
        persist_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Initializing ChromaDB | dir={} collection={}",
            persist_dir,
            self._settings.CHROMA_COLLECTION_NAME,
        )

        embedding_fn = EmbeddingsFactory(self._settings).create()

        client = chromadb.PersistentClient(
            path=str(persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        collection = client.get_or_create_collection(
            name=self._settings.CHROMA_COLLECTION_NAME,
            embedding_function=embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

        logger.info(
            "ChromaDB ready | total_chunks={}",
            collection.count(),
        )
        return collection

    def add_documents(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]],
        ids: list[str],
    ) -> None:
        """Thêm chunks vào collection, upsert để tránh duplicate."""
        if not texts:
            return

        logger.debug("Adding {} chunks to ChromaDB", len(texts))

        # Serialize metadata values thành string (ChromaDB không nhận nested objects)
        safe_metadatas = [
            {k: str(v) for k, v in meta.items()}
            for meta in metadatas
        ]

        self._collection.upsert(
            documents=texts,
            metadatas=safe_metadatas,
            ids=ids,
        )

        logger.info("Added {} chunks to ChromaDB", len(texts))

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Tìm kiếm semantic — trả về top_k chunks liên quan nhất.

        Returns:
            List[{"text": str, "metadata": dict, "distance": float}]
        """
        logger.debug("Querying ChromaDB | query='{}' top_k={}", query_text[:50], top_k)

        kwargs: dict[str, Any] = {
            "query_texts": [query_text],
            "n_results": min(top_k, self._collection.count() or 1),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = self._collection.query(**kwargs)

        # Flatten kết quả (ChromaDB trả về nested list)
        output = []
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for text, meta, dist in zip(documents, metadatas, distances):
            output.append({
                "text": text,
                "metadata": meta,
                "distance": round(dist, 4),
            })

        return output

    def delete_document(self, document_id: str) -> int:
        """Xóa tất cả chunk của một tài liệu theo document_id."""
        logger.info("Deleting document from ChromaDB | document_id={}", document_id)

        # Lấy IDs của chunks thuộc document_id
        results = self._collection.get(
            where={"document_id": document_id},
            include=["metadatas"],
        )
        chunk_ids = results.get("ids", [])

        if chunk_ids:
            self._collection.delete(ids=chunk_ids)
            logger.info("Deleted {} chunks | document_id={}", len(chunk_ids), document_id)

        return len(chunk_ids)

    def get_document_ids(self) -> list[str]:
        """Trả về danh sách document_id đã được index."""
        if self._collection.count() == 0:
            return []

        results = self._collection.get(include=["metadatas"])
        seen = set()
        doc_ids = []
        for meta in results.get("metadatas", []):
            doc_id = meta.get("document_id")
            if doc_id and doc_id not in seen:
                seen.add(doc_id)
                doc_ids.append(doc_id)

        return doc_ids

    def count(self) -> int:
        """Tổng số chunk trong collection."""
        return self._collection.count()
