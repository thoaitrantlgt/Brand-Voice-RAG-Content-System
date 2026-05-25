"""
services/document_service.py — Document Ingestion & Management Business Logic
SRP: Chỉ xử lý business logic cho document pipeline.
DIP: Depend vào IDocumentProcessor và IVectorStore abstractions.
"""
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import Settings
from app.core.exceptions import InvalidInputError, ToolExecutionError
from app.core.interfaces import IDocumentProcessor, IVectorStore
from app.core.logging import logger
from app.schemas.document import (
    DocumentInfo,
    ListDocumentsResponse,
    SearchKnowledgeBaseResponse,
    SearchResultItem,
    UploadDocumentResponse,
    DeleteDocumentResponse,
)
from app.rag.retrieval_engine import RetrievalEngine


class DocumentService:
    """
    Orchestrate toàn bộ pipeline xử lý tài liệu:
    Upload → Validate → Process (LangChain) → Index (ChromaDB).

    DIP: Nhận processor và vector_store qua constructor injection.
    Không biết implementation cụ thể là LangChain hay ChromaDB.
    """

    def __init__(
        self,
        processor: IDocumentProcessor,
        vector_store: IVectorStore,
        settings: Settings,
    ) -> None:
        self._processor = processor
        self._store = vector_store
        self._settings = settings
        self._retrieval = RetrievalEngine(vector_store, settings)
        # In-memory metadata store (Phase 3: thay bằng SQLite/PostgreSQL)
        self._doc_metadata: dict[str, dict] = {}

    async def upload_and_index(
        self,
        file_path: Path,
        filename: str,
    ) -> UploadDocumentResponse:
        """
        Nhận file đã upload → validate → chunk → index vào ChromaDB.

        Args:
            file_path: Path đến file tạm đã lưu.
            filename: Tên file gốc từ client.

        Returns:
            UploadDocumentResponse với document_id và số chunks đã index.

        Raises:
            InvalidInputError: Nếu extension không hỗ trợ hoặc file quá lớn.
            ToolExecutionError: Nếu processing thất bại.
        """
        ext = Path(filename).suffix.lstrip(".").lower()

        # Validate extension
        if ext not in self._settings.ALLOWED_EXTENSIONS:
            raise InvalidInputError(
                f"Định dạng '.{ext}' không được hỗ trợ.",
                {
                    "allowed": self._settings.ALLOWED_EXTENSIONS,
                    "received": ext,
                },
            )

        # Validate file size
        size_mb = file_path.stat().st_size / (1024 * 1024)
        if size_mb > self._settings.MAX_UPLOAD_SIZE_MB:
            raise InvalidInputError(
                f"File quá lớn ({size_mb:.1f}MB). Tối đa {self._settings.MAX_UPLOAD_SIZE_MB}MB.",
                {"size_mb": size_mb, "max_mb": self._settings.MAX_UPLOAD_SIZE_MB},
            )

        document_id = str(uuid.uuid4())
        logger.info(
            "Uploading document | filename={} document_id={}",
            filename,
            document_id,
        )

        # Process: load + chunk
        processed = self._processor.process(file_path, document_id)

        # Index vào ChromaDB
        texts = [chunk.text for chunk in processed.chunks]
        metadatas = [chunk.metadata for chunk in processed.chunks]
        ids = [f"{document_id}_{i}" for i in range(processed.total_chunks)]

        self._store.add_documents(texts=texts, metadatas=metadatas, ids=ids)

        # Lưu metadata
        self._doc_metadata[document_id] = {
            "document_id": document_id,
            "filename": filename,
            "total_chunks": processed.total_chunks,
            "extension": ext,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }

        return UploadDocumentResponse(
            document_id=document_id,
            filename=filename,
            total_chunks=processed.total_chunks,
        )

    async def list_documents(self) -> ListDocumentsResponse:
        """Trả về danh sách tất cả tài liệu đã index."""
        total_chunks = self._store.count()

        documents = [
            DocumentInfo(**meta)
            for meta in self._doc_metadata.values()
        ]

        return ListDocumentsResponse(
            documents=documents,
            total_documents=len(documents),
            total_chunks=total_chunks,
        )

    async def delete_document(self, document_id: str) -> DeleteDocumentResponse:
        """Xóa tài liệu khỏi ChromaDB và metadata store."""
        if document_id not in self._doc_metadata:
            raise InvalidInputError(
                f"Tài liệu '{document_id}' không tồn tại.",
                {"document_id": document_id},
            )

        deleted_chunks = self._store.delete_document(document_id)
        del self._doc_metadata[document_id]

        return DeleteDocumentResponse(
            document_id=document_id,
            deleted_chunks=deleted_chunks,
            message=f"Đã xóa tài liệu và {deleted_chunks} chunks khỏi Knowledge Hub.",
        )

    async def search(
        self,
        query: str,
        top_k: int = 5,
        document_id: str | None = None,
    ) -> SearchKnowledgeBaseResponse:
        """Thực hiện semantic search và trả về kết quả đã format."""
        results_raw = self._retrieval.retrieve(
            query=query,
            top_k=top_k,
            document_id=document_id,
        )

        results = []
        for item in results_raw:
            meta = item["metadata"]
            results.append(SearchResultItem(
                text=item["text"],
                filename=meta.get("filename", "unknown"),
                chunk_index=int(meta.get("chunk_index", 0)),
                relevance_score=round(1 - item["distance"], 4),
                metadata=meta,
            ))

        return SearchKnowledgeBaseResponse(
            query=query,
            results=results,
            total_results=len(results),
        )
