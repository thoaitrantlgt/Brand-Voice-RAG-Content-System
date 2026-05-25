"""
interfaces/base_document_processor.py — Document Processor Abstract Interface
SRP + ISP: Processor chỉ chịu trách nhiệm đọc file và trả về chunks.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DocumentChunk:
    """Value Object đại diện cho một chunk văn bản đã xử lý."""
    text: str
    metadata: dict
    chunk_index: int


@dataclass
class ProcessedDocument:
    """Kết quả xử lý một tài liệu — chứa danh sách chunks và metadata gốc."""
    document_id: str
    filename: str
    total_chunks: int
    chunks: list[DocumentChunk]
    source_metadata: dict


class IDocumentProcessor(ABC):
    """
    Contract cho việc load và chunk tài liệu.
    Implementation cụ thể sử dụng LangChain Document Loaders.
    """

    @abstractmethod
    def process(self, file_path: Path, document_id: str) -> ProcessedDocument:
        """
        Đọc file, chia thành chunks, trả về ProcessedDocument.

        Args:
            file_path: Đường dẫn tuyệt đối đến file.
            document_id: ID duy nhất để track tài liệu trong vector store.

        Returns:
            ProcessedDocument với danh sách chunks đã sẵn sàng index.

        Raises:
            ToolExecutionError: Nếu file không đọc được hoặc format không hỗ trợ.
        """
        ...

    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """Trả về danh sách extension file được hỗ trợ (vd: ['pdf', 'txt'])."""
        ...
