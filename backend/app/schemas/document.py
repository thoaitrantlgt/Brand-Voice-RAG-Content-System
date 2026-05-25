"""
schemas/document.py — Pydantic Schemas cho Document Upload API (Phase 2)
SRP: Chỉ định nghĩa cấu trúc dữ liệu — không có business logic.
"""
from datetime import datetime

from pydantic import BaseModel, Field


# ===== Response Schemas =====

class DocumentInfo(BaseModel):
    """Thông tin tóm tắt về một tài liệu đã upload."""
    document_id: str
    filename: str
    total_chunks: int
    extension: str
    uploaded_at: str


class UploadDocumentResponse(BaseModel):
    """Response sau khi upload và index tài liệu thành công."""
    document_id: str = Field(description="ID duy nhất của tài liệu vừa upload.")
    filename: str
    total_chunks: int = Field(description="Số chunks đã được index vào ChromaDB.")
    message: str = "Tài liệu đã được upload và index thành công."
    status: str = "success"


class ListDocumentsResponse(BaseModel):
    """Response danh sách tài liệu đã index."""
    documents: list[DocumentInfo]
    total_documents: int
    total_chunks: int
    status: str = "success"


class DeleteDocumentResponse(BaseModel):
    """Response sau khi xóa tài liệu."""
    document_id: str
    deleted_chunks: int
    message: str
    status: str = "success"


# ===== Search Schemas =====

class SearchKnowledgeBaseRequest(BaseModel):
    """Request tìm kiếm trong Knowledge Hub."""
    query: str = Field(
        min_length=3,
        description="Câu query tìm kiếm bằng ngôn ngữ tự nhiên.",
        examples=["best practices for REST API design"],
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Số kết quả tối đa trả về.",
    )
    document_id: str | None = Field(
        default=None,
        description="Lọc kết quả chỉ từ tài liệu cụ thể.",
    )


class SearchResultItem(BaseModel):
    """Một chunk kết quả từ semantic search."""
    text: str
    filename: str
    chunk_index: int
    relevance_score: float = Field(description="Độ liên quan từ 0-1 (1 = hoàn toàn liên quan).")
    metadata: dict


class SearchKnowledgeBaseResponse(BaseModel):
    """Response từ semantic search trong Knowledge Hub."""
    query: str
    results: list[SearchResultItem]
    total_results: int
    status: str = "success"
