"""
interfaces/base_vector_store.py — Vector Store Abstract Interface
ISP: Chỉ định nghĩa các thao tác thiết yếu với vector DB.
OCP: Swap ChromaDB → Pinecone/Qdrant chỉ cần implement interface này.
"""
from abc import ABC, abstractmethod
from typing import Any


class IVectorStore(ABC):
    """
    Contract cho vector store — không phụ thuộc vào ChromaDB cụ thể.
    Bất kỳ vector DB nào implement interface này đều dùng được trong hệ thống.
    """

    @abstractmethod
    def add_documents(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]],
        ids: list[str],
    ) -> None:
        """
        Thêm danh sách text đã chunk vào vector store.

        Args:
            texts: Nội dung các chunk.
            metadatas: Metadata đi kèm (filename, page, source, v.v.).
            ids: ID duy nhất cho mỗi chunk.
        """
        ...

    @abstractmethod
    def query(
        self,
        query_text: str,
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Tìm kiếm semantic các chunk liên quan đến query.

        Args:
            query_text: Câu query tìm kiếm.
            top_k: Số kết quả tối đa trả về.
            where: Bộ lọc metadata (vd: {"document_id": "abc"}).

        Returns:
            List dict chứa 'text', 'metadata', và 'distance'.
        """
        ...

    @abstractmethod
    def delete_document(self, document_id: str) -> int:
        """
        Xóa tất cả chunk thuộc về một tài liệu.

        Args:
            document_id: ID tài liệu cần xóa.

        Returns:
            Số chunk đã xóa.
        """
        ...

    @abstractmethod
    def get_document_ids(self) -> list[str]:
        """Trả về danh sách ID tài liệu đã được index."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Trả về tổng số chunk trong store."""
        ...
