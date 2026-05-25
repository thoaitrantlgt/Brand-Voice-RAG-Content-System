"""
rag/document_processor.py — LangChain Document Loader + Chunker
SRP: Chỉ chịu trách nhiệm đọc file và chia thành chunks.
OCP: Thêm loại file mới → thêm loader vào registry, không sửa logic chính.
"""
import uuid
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    UnstructuredMarkdownLoader,
    Docx2txtLoader,
)
from langchain_core.documents import Document

from app.core.config import Settings
from app.core.exceptions import ToolExecutionError
from app.core.interfaces import IDocumentProcessor, DocumentChunk, ProcessedDocument
from app.core.logging import logger


# Registry: map extension → LangChain Loader class
# OCP: thêm loader mới chỉ cần thêm vào dict này
_LOADER_REGISTRY: dict[str, type] = {
    "pdf": PyPDFLoader,
    "txt": TextLoader,
    "md": UnstructuredMarkdownLoader,
    "docx": Docx2txtLoader,
}


class LangChainDocumentProcessor(IDocumentProcessor):
    """
    Implement IDocumentProcessor dùng LangChain Document Loaders.
    Hỗ trợ PDF, TXT, MD, DOCX.
    Chunking dùng RecursiveCharacterTextSplitter để tôn trọng cấu trúc văn bản.
    """

    def __init__(self, settings: Settings) -> None:
        """DIP: Nhận Settings từ ngoài."""
        self._settings = settings
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def supported_extensions(self) -> list[str]:
        return list(_LOADER_REGISTRY.keys())

    def process(self, file_path: Path, document_id: str) -> ProcessedDocument:
        """
        Đọc file → split thành chunks → trả về ProcessedDocument.

        Args:
            file_path: Đường dẫn đến file đã upload.
            document_id: ID unique để track tài liệu trong ChromaDB.

        Returns:
            ProcessedDocument sẵn sàng để index.

        Raises:
            ToolExecutionError: Nếu extension không hỗ trợ hoặc file lỗi.
        """
        ext = file_path.suffix.lstrip(".").lower()

        if ext not in _LOADER_REGISTRY:
            raise ToolExecutionError(
                f"Định dạng file '.{ext}' không được hỗ trợ.",
                {"supported": self.supported_extensions(), "file": str(file_path)},
            )

        logger.info(
            "Processing document | file={} document_id={}",
            file_path.name,
            document_id,
        )

        try:
            loader_cls = _LOADER_REGISTRY[ext]
            loader = loader_cls(str(file_path))
            raw_docs: list[Document] = loader.load()
        except Exception as e:
            raise ToolExecutionError(
                f"Không thể đọc file '{file_path.name}': {e}",
                {"file": str(file_path), "extension": ext},
            ) from e

        # Split thành chunks
        split_docs = self._splitter.split_documents(raw_docs)

        chunks = []
        for i, doc in enumerate(split_docs):
            # Gắn document_id vào metadata của mỗi chunk
            doc.metadata["document_id"] = document_id
            doc.metadata["filename"] = file_path.name
            doc.metadata["chunk_index"] = i

            chunks.append(DocumentChunk(
                text=doc.page_content,
                metadata=doc.metadata,
                chunk_index=i,
            ))

        logger.info(
            "Document processed | file={} total_chunks={}",
            file_path.name,
            len(chunks),
        )

        return ProcessedDocument(
            document_id=document_id,
            filename=file_path.name,
            total_chunks=len(chunks),
            chunks=chunks,
            source_metadata={
                "file_path": str(file_path),
                "extension": ext,
                "raw_page_count": len(raw_docs),
            },
        )
