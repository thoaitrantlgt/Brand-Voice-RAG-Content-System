"""
rag/retrieval_engine.py — RAG Retrieval Engine
SRP: Chỉ chịu trách nhiệm truy xuất ngữ cảnh từ vector store.
DIP: Depend vào IVectorStore abstraction, không phải ChromaDB cụ thể.
"""
from typing import Any

from app.core.config import Settings
from app.core.interfaces import IVectorStore
from app.core.logging import logger


class RetrievalEngine:
    """
    Encapsulate logic truy xuất semantic từ vector store.
    Trả về context string sẵn sàng để inject vào prompt của agent.

    DIP: Nhận IVectorStore thay vì ChromaVectorStore trực tiếp.
    """

    def __init__(self, vector_store: IVectorStore, settings: Settings) -> None:
        self._store = vector_store
        self._top_k = settings.RETRIEVAL_TOP_K

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        document_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Truy xuất top_k chunks liên quan nhất.

        Args:
            query: Câu query từ agent.
            top_k: Override số kết quả (dùng setting mặc định nếu None).
            document_id: Lọc chỉ trong tài liệu cụ thể (optional).

        Returns:
            List dict [{"text": str, "metadata": dict, "distance": float}].
        """
        k = top_k or self._top_k
        where = {"document_id": document_id} if document_id else None

        logger.debug("Retrieving context | query='{}' top_k={}", query[:60], k)

        results = self._store.query(query_text=query, top_k=k, where=where)

        logger.debug("Retrieved {} chunks", len(results))
        return results

    def retrieve_as_context(
        self,
        query: str,
        top_k: int | None = None,
        document_id: str | None = None,
    ) -> str:
        """
        Convenience method — trả về context string đã format,
        sẵn sàng để inject vào task description của CrewAI agent.

        Returns:
            String format:
            "--- Tài liệu tham khảo ---\\n[1] (filename, page X)\\n<text>\\n\\n..."
        """
        chunks = self.retrieve(query, top_k, document_id)

        if not chunks:
            return "Không tìm thấy tài liệu tham khảo liên quan."

        lines = ["--- Tài liệu tham khảo (từ Knowledge Hub) ---\n"]
        for i, chunk in enumerate(chunks, 1):
            meta = chunk["metadata"]
            filename = meta.get("filename", "unknown")
            page = meta.get("page", "")
            page_info = f", trang {page}" if page else ""

            lines.append(
                f"[{i}] Nguồn: {filename}{page_info} "
                f"(độ liên quan: {1 - chunk['distance']:.0%})\n"
                f"{chunk['text']}\n"
            )

        return "\n".join(lines)
