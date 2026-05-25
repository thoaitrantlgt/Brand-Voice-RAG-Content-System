"""
schemas/content.py — Pydantic Schemas cho Content API
SRP: Chỉ định nghĩa cấu trúc dữ liệu request/response — không chứa business logic.
"""
from pydantic import BaseModel, Field


# ===== Request Schemas =====

class GenerateTitlesRequest(BaseModel):
    """Request để Planner Agent tạo danh sách tiêu đề."""
    keywords: list[str] = Field(
        min_length=1,
        max_length=10,
        description="Danh sách từ khóa cần phân tích (tối đa 10).",
        examples=[["AI writing tool", "content automation"]],
    )
    use_web_search: bool = Field(
        default=False,
        description="Bật tìm kiếm web để Planner Agent tham khảo xu hướng hiện tại.",
    )


class GenerateContentRequest(BaseModel):
    """Request để Writer + Editor Agent tạo bài viết hoàn chỉnh."""
    keywords: list[str] = Field(
        min_length=1,
        description="Từ khóa chính cần tối ưu trong bài viết.",
    )
    selected_title: str = Field(
        min_length=10,
        max_length=200,
        description="Tiêu đề đã được người dùng chọn từ bước Planner.",
        examples=["10 cách dùng AI để viết blog nhanh hơn 10x"],
    )
    outline: list[str] = Field(
        default=[],
        description="Outline tùy chỉnh (nếu không cung cấp, dùng outline từ Planner).",
    )
    use_web_search: bool = Field(
        default=False,
        description="Bật tìm kiếm web để Writer Agent bổ sung thông tin.",
    )


class RewriteRequest(BaseModel):
    """Request để sửa đổi một đoạn văn bản dựa trên feedback."""
    original_text: str = Field(
        min_length=1,
        description="Đoạn văn bản gốc cần sửa.",
    )
    feedback: str = Field(
        min_length=1,
        description="Yêu cầu sửa đổi (comment của người dùng).",
    )


# ===== Response Schemas =====

class PostTitleItem(BaseModel):
    """Một tiêu đề bài viết từ Planner Agent."""
    keyword: str
    title: str
    seo_title: str
    outline: list[str]


class GenerateTitlesResponse(BaseModel):
    """Response từ Planner API."""
    titles: list[PostTitleItem]
    search_links: list[str] = Field(
        default=[],
        description="Danh sách URL đã tìm kiếm (chỉ có khi use_web_search=True).",
    )
    status: str = "success"


class GenerateContentResponse(BaseModel):
    """Response từ Content Generation API."""
    optimized_content: str = Field(description="Bài viết đã tối ưu SEO (Markdown).")
    title_tag: str = Field(description="SEO title tag (≤60 ký tự).")
    meta_description: str = Field(description="Meta description (150-160 ký tự).")
    status: str = "success"


class RewriteResponse(BaseModel):
    """Response từ API Re-write."""
    rewritten_text: str = Field(description="Đoạn văn bản đã được AI sửa lại.")
    status: str = "success"


class ErrorResponse(BaseModel):
    """Chuẩn hóa error response cho tất cả API endpoints."""
    error: str
    details: dict = {}
    status: str = "error"
