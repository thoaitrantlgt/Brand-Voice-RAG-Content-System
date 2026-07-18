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
    DOCUMENT_PURPOSES,
    DocumentInfo,
    ListDocumentsResponse,
    SearchKnowledgeBaseResponse,
    SearchResultItem,
    UploadDocumentResponse,
    DeleteDocumentResponse,
)
from app.rag.retrieval_engine import RetrievalEngine
from app.repositories.document_repository import DocumentRepository


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
        repository: DocumentRepository | None = None,
    ) -> None:
        self._processor = processor
        self._store = vector_store
        self._settings = settings
        self._retrieval = RetrievalEngine(vector_store, settings)
        self._repository = repository
        # In-memory metadata store (Phase 3: thay bằng SQLite/PostgreSQL)
        self._doc_metadata: dict[str, dict] = {}

    @property
    def vector_store(self) -> IVectorStore:
        """Expose the shared vector store for workflows that operate on indexed content."""
        return self._store

    def get_document_metadata(self, document_id: str) -> dict | None:
        if self._repository:
            return self._repository.get(document_id)
        return self._doc_metadata.get(document_id)

    async def upload_and_index(
        self,
        file_path: Path,
        filename: str,
        purpose: str = "knowledge",
        project_id: str = "default",
        profile_id: str | None = None,
        cluster: str | None = None,
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
        purpose = purpose.strip().lower()
        project_id = project_id.strip() or "default"
        profile_id = profile_id.strip() if profile_id else None
        cluster = (cluster or ("knowledge" if purpose == "both" else purpose)).strip().lower()

        if purpose not in DOCUMENT_PURPOSES:
            raise InvalidInputError(
                f"Document purpose '{purpose}' is not supported.",
                {"allowed": sorted(DOCUMENT_PURPOSES), "received": purpose},
            )
        if cluster not in {"knowledge", "brand_voice", "evaluation"}:
            raise InvalidInputError(
                f"Document cluster '{cluster}' is not supported.",
                {"allowed": ["knowledge", "brand_voice", "evaluation"], "received": cluster},
            )

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
            "Uploading document | filename={} document_id={} purpose={}",
            filename,
            document_id,
            purpose,
        )

        # Process: load + chunk
        processed = self._processor.process(file_path, document_id)

        # Index vào ChromaDB
        texts = [chunk.text for chunk in processed.chunks]
        metadatas = []
        for chunk in processed.chunks:
            metadata = dict(chunk.metadata)
            metadata["purpose"] = purpose
            metadata["cluster"] = cluster
            metadata["project_id"] = project_id
            if profile_id:
                metadata["profile_id"] = profile_id
            metadatas.append(metadata)
        ids = [f"{document_id}_{i}" for i in range(processed.total_chunks)]

        self._store.add_documents(texts=texts, metadatas=metadatas, ids=ids)

        # Lưu metadata
        document_meta = {
            "document_id": document_id,
            "filename": filename,
            "total_chunks": processed.total_chunks,
            "extension": ext,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "purpose": purpose,
            "project_id": project_id,
            "profile_id": profile_id,
            "cluster": cluster,
        }
        if self._repository:
            self._repository.create(document_meta)
        else:
            self._doc_metadata[document_id] = document_meta

        return UploadDocumentResponse(
            document_id=document_id,
            filename=filename,
            total_chunks=processed.total_chunks,
            purpose=purpose,
            project_id=project_id,
            profile_id=profile_id,
            cluster=cluster,
        )

    async def list_documents(
        self, project_id: str | None = None, cluster: str | None = None
    ) -> ListDocumentsResponse:
        """Trả về danh sách tất cả tài liệu đã index."""
        if self._repository:
            metadata = self._repository.list(project_id=project_id, cluster=cluster)
        else:
            metadata = [
                item
                for item in self._doc_metadata.values()
                if (not project_id or item.get("project_id") == project_id)
                and (not cluster or item.get("cluster") == cluster)
            ]
        total_chunks = sum(int(item.get("total_chunks", 0)) for item in metadata)
        documents = [DocumentInfo(**meta) for meta in metadata]

        return ListDocumentsResponse(
            documents=documents,
            total_documents=len(documents),
            total_chunks=total_chunks,
        )

    async def delete_document(self, document_id: str) -> DeleteDocumentResponse:
        """Xóa tài liệu khỏi ChromaDB và metadata store."""
        existing = self._repository.get(document_id) if self._repository else self._doc_metadata.get(document_id)
        if not existing:
            raise InvalidInputError(
                f"Tài liệu '{document_id}' không tồn tại.",
                {"document_id": document_id},
            )

        deleted_chunks = self._store.delete_document(document_id)
        if self._repository:
            self._repository.delete(document_id)
        else:
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
        project_id: str = "default",
        cluster: str = "knowledge",
        profile_id: str | None = None,
    ) -> SearchKnowledgeBaseResponse:
        """Thực hiện semantic search và trả về kết quả đã format."""
        results_raw = self._retrieval.retrieve(
            query=query,
            top_k=top_k,
            document_id=document_id,
            project_id=project_id,
            cluster=cluster,
            profile_id=profile_id,
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
