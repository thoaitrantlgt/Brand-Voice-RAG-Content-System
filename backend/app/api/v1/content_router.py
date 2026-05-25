"""
api/v1/content_router.py — Content Generation API Endpoints
SRP: Router chỉ xử lý HTTP request/response — delegate logic cho Service.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import Settings, get_settings
from app.core.exceptions import ContentGenerationError
from app.core.logging import logger
from app.crews.content_crew import ContentCrew
from app.schemas.content import (
    GenerateTitlesRequest,
    GenerateContentRequest,
    GenerateContentResponse,
    GenerateTitlesResponse,
    RewriteRequest,
    RewriteResponse,
    ErrorResponse,
)
from app.services.content_service import ContentService
from app.rag.vector_store import ChromaVectorStore
from functools import lru_cache

router = APIRouter(prefix="/content", tags=["Content Generation"])


@lru_cache(maxsize=1)
def _get_content_service() -> ContentService:
    settings = get_settings()
    vector_store = ChromaVectorStore(settings)
    crew = ContentCrew(settings, vector_store=vector_store)
    return ContentService(crew=crew)

def get_content_service() -> ContentService:
    """
    FastAPI Dependency: trả về ContentService singleton với ContentCrew + RAG.
    """
    return _get_content_service()


@router.post(
    "/titles",
    response_model=GenerateTitlesResponse,
    responses={500: {"model": ErrorResponse}},
    summary="Tạo plan nháp bài viết",
    description="Chạy Planner Agent để phân tích từ khóa và tạo danh sách plan nháp có thể chỉnh sửa.",
)
async def generate_titles(
    request: GenerateTitlesRequest,
    service: ContentService = Depends(get_content_service),
) -> GenerateTitlesResponse:
    """
    **Bước 1 của pipeline**: Planner Agent phân tích từ khóa và tạo plan nháp.
    Người dùng chỉnh tiêu đề/outline trước khi gọi /generate.
    """
    logger.info("POST /content/titles | keywords={}", request.keywords)

    try:
        result = await service.generate_titles(
            keywords=request.keywords,
            use_web_search=request.use_web_search,
        )
        return GenerateTitlesResponse(**result)

    except ContentGenerationError as e:
        logger.error("Title generation failed | {}", e.message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": e.message, "details": e.details},
        )


@router.post(
    "/generate",
    response_model=GenerateContentResponse,
    responses={500: {"model": ErrorResponse}},
    summary="Tạo bài viết hoàn chỉnh",
    description="Chạy Writer + Editor Agent để tạo bài viết tối ưu SEO từ tiêu đề đã chọn.",
)
async def generate_content(
    request: GenerateContentRequest,
    service: ContentService = Depends(get_content_service),
) -> GenerateContentResponse:
    """
    **Bước 2 của pipeline**: Writer viết bài → Editor tối ưu SEO.
    Yêu cầu người dùng đã chọn tiêu đề từ bước /titles.
    """
    logger.info("POST /content/generate | title={}", request.selected_title)

    try:
        result = await service.generate_content(
            keywords=request.keywords,
            selected_title=request.selected_title,
            outline=request.outline or None,
            use_web_search=request.use_web_search,
        )
        return GenerateContentResponse(**result)

    except ContentGenerationError as e:
        logger.error("Content generation failed | {}", e.message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": e.message, "details": e.details},
        )

@router.post(
    "/rewrite",
    response_model=RewriteResponse,
    responses={500: {"model": ErrorResponse}},
    summary="Sửa đoạn văn bản (Inline Comment)",
    description="Sửa đổi một đoạn văn bản theo feedback người dùng (độc lập, không chạy qua CrewAI pipeline).",
)
async def rewrite_content(
    request: RewriteRequest,
    service: ContentService = Depends(get_content_service),
) -> RewriteResponse:
    """
    **Bước 3 của pipeline**: Giao tiếp Human-in-the-Loop.
    Chỉnh sửa trực tiếp đoạn văn trên giao diện.
    """
    logger.info("POST /content/rewrite")

    try:
        result = await service.rewrite_content(
            original_text=request.original_text,
            feedback=request.feedback,
        )
        return RewriteResponse(**result)

    except ContentGenerationError as e:
        logger.error("Rewrite failed | {}", e.message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": e.message, "details": e.details},
        )
