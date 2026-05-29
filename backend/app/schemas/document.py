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


# ===== Brand Voice Training Schemas =====

class TrainBrandVoiceRequest(BaseModel):
    """Request to extract a brand voice profile from existing blog documents."""
    company_name: str | None = Field(
        default=None,
        description="Optional company name to store in the generated brand voice profile.",
    )
    document_ids: list[str] = Field(
        default=[],
        description="Specific document IDs to use. Empty means all uploaded source documents.",
    )
    min_documents: int = Field(
        default=20,
        ge=1,
        le=30,
        description="Recommended minimum number of high-quality blog documents.",
    )
    max_documents: int = Field(
        default=30,
        ge=1,
        le=30,
        description="Maximum source documents to analyze.",
    )
    target_audience: str | None = Field(
        default=None,
        description="Primary audience persona for the brand voice profile.",
    )
    brand_values: list[str] = Field(
        default=[],
        description="Optional values or principles the brand should communicate.",
    )
    channels: list[str] = Field(
        default=["blog", "email", "social", "support", "ads"],
        description="Channels that need channel-specific voice guidance.",
    )


class BrandVoiceProfileResponse(BaseModel):
    """Response after training or fetching the active brand voice profile."""
    profile_id: str
    company_name: str
    source_document_count: int
    profile_path: str
    dataset_path: str | None = None
    dpo_dataset_path: str | None = None
    indexed_chunks: int = 0
    profile_markdown: str
    warnings: list[str] = Field(default=[])
    status: str = "success"


class BrandVoiceEvaluateRequest(BaseModel):
    """Request to score generated content against the active brand voice profile."""
    content: str = Field(min_length=20, description="Generated content to evaluate.")
    channel: str = Field(default="blog", description="Content channel, e.g. blog/email/social/support/ads.")
    content_type: str = Field(default="blog_post", description="Specific content format being reviewed.")


class BrandVoiceEvaluateResponse(BaseModel):
    """Brand voice quality score and reviewer checklist."""
    profile_id: str
    channel: str
    content_type: str
    overall_score: int
    dimension_scores: dict
    violations: list[str] = Field(default=[])
    recommendations: list[str] = Field(default=[])
    reviewer_checklist: list[str] = Field(default=[])
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
