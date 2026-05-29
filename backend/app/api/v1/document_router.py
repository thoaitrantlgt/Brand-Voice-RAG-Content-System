"""
api/v1/document_router.py — Document Upload & Knowledge Hub API (Phase 2)
SRP: Router chỉ xử lý HTTP — delegate hoàn toàn cho DocumentService.

Endpoints:
  POST   /documents/upload   — Upload & index tài liệu
  GET    /documents          — Danh sách tài liệu đã index
  DELETE /documents/{id}     — Xóa tài liệu
  POST   /documents/search   — Semantic search trong Knowledge Hub
"""
import shutil
from pathlib import Path
from functools import lru_cache

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.config import Settings, get_settings
from app.core.exceptions import InvalidInputError, ToolExecutionError
from app.core.logging import logger
from app.rag.document_processor import LangChainDocumentProcessor
from app.rag.vector_store import ChromaVectorStore
from app.schemas.document import (
    DeleteDocumentResponse,
    ListDocumentsResponse,
    BrandVoiceEvaluateRequest,
    BrandVoiceEvaluateResponse,
    SearchKnowledgeBaseRequest,
    SearchKnowledgeBaseResponse,
    TrainBrandVoiceRequest,
    BrandVoiceProfileResponse,
    UploadDocumentResponse,
)
from app.services.brand_voice_service import BrandVoiceService
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["Knowledge Hub (RAG)"])


# Singleton DocumentService — tái sử dụng ChromaDB connection
@lru_cache(maxsize=1)
def _get_document_service() -> DocumentService:
    """
    Tạo DocumentService singleton — ChromaVectorStore chỉ khởi tạo 1 lần.
    lru_cache đảm bảo connection ChromaDB được tái sử dụng giữa các request.
    """
    settings = get_settings()
    processor = LangChainDocumentProcessor(settings)
    vector_store = ChromaVectorStore(settings)
    return DocumentService(
        processor=processor,
        vector_store=vector_store,
        settings=settings,
    )


def get_document_service() -> DocumentService:
    return _get_document_service()


def get_brand_voice_service() -> BrandVoiceService:
    settings = get_settings()
    vector_store = _get_document_service().vector_store
    return BrandVoiceService(vector_store=vector_store, settings=settings)


@router.post(
    "/upload",
    response_model=UploadDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload tài liệu vào Knowledge Hub",
    description=(
        "Upload file (PDF, TXT, MD, DOCX) để Chunk và Index vào ChromaDB. "
        "Writer Agent sẽ tự động tìm kiếm trong Knowledge Hub khi viết bài."
    ),
)
async def upload_document(
    file: UploadFile = File(..., description="File cần upload (PDF, TXT, MD, DOCX)."),
    service: DocumentService = Depends(get_document_service),
    settings: Settings = Depends(get_settings),
) -> UploadDocumentResponse:
    """Upload và index tài liệu vào ChromaDB Knowledge Hub."""
    logger.info("POST /documents/upload | filename={}", file.filename)

    # Lưu file tạm
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    temp_path = upload_dir / (file.filename or "upload")

    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        result = await service.upload_and_index(
            file_path=temp_path,
            filename=file.filename or "unknown",
        )
        return result

    except InvalidInputError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": e.message, "details": e.details},
        )
    except ToolExecutionError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": e.message, "details": e.details},
        )


@router.get(
    "",
    response_model=ListDocumentsResponse,
    summary="Danh sách tài liệu đã index",
)
async def list_documents(
    service: DocumentService = Depends(get_document_service),
) -> ListDocumentsResponse:
    """Trả về danh sách tất cả tài liệu đã được index vào Knowledge Hub."""
    return await service.list_documents()


@router.delete(
    "/{document_id}",
    response_model=DeleteDocumentResponse,
    summary="Xóa tài liệu khỏi Knowledge Hub",
)
async def delete_document(
    document_id: str,
    service: DocumentService = Depends(get_document_service),
) -> DeleteDocumentResponse:
    """Xóa tài liệu và tất cả chunks liên quan khỏi ChromaDB."""
    logger.info("DELETE /documents/{}", document_id)

    try:
        return await service.delete_document(document_id)
    except InvalidInputError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": e.message, "details": e.details},
        )


@router.post(
    "/search",
    response_model=SearchKnowledgeBaseResponse,
    summary="Tìm kiếm semantic trong Knowledge Hub",
    description="Tìm kiếm các đoạn văn bản liên quan trong tài liệu đã upload.",
)
async def search_knowledge_base(
    request: SearchKnowledgeBaseRequest,
    service: DocumentService = Depends(get_document_service),
) -> SearchKnowledgeBaseResponse:
    """Semantic search trong ChromaDB Knowledge Hub."""
    logger.info("POST /documents/search | query='{}'", request.query[:50])

    return await service.search(
        query=request.query,
        top_k=request.top_k,
        document_id=request.document_id,
    )


@router.post(
    "/brand-voice/train",
    response_model=BrandVoiceProfileResponse,
    summary="Train brand voice profile from existing blog documents",
    description=(
        "Analyze 20-30 high-quality indexed blog documents, extract tone/vocabulary/"
        "syntax/presentation rules, write an SFT JSONL dataset, and index the profile "
        "back into the Knowledge Hub for RAG."
    ),
)
async def train_brand_voice(
    request: TrainBrandVoiceRequest,
    service: BrandVoiceService = Depends(get_brand_voice_service),
) -> BrandVoiceProfileResponse:
    logger.info("POST /documents/brand-voice/train | selected_docs={}", len(request.document_ids))

    try:
        return await service.train(request)
    except InvalidInputError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": e.message, "details": e.details},
        )
    except ToolExecutionError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": e.message, "details": e.details},
        )


@router.get(
    "/brand-voice/profile",
    response_model=BrandVoiceProfileResponse,
    summary="Get active brand voice profile",
)
async def get_brand_voice_profile(
    service: BrandVoiceService = Depends(get_brand_voice_service),
) -> BrandVoiceProfileResponse:
    try:
        return await service.get_active_profile()
    except InvalidInputError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": e.message, "details": e.details},
        )


@router.post(
    "/brand-voice/evaluate",
    response_model=BrandVoiceEvaluateResponse,
    summary="Evaluate content against active brand voice profile",
    description=(
        "Score generated content before publishing. Returns a voice deviation score, "
        "violations, recommendations, and a human reviewer checklist."
    ),
)
async def evaluate_brand_voice(
    request: BrandVoiceEvaluateRequest,
    service: BrandVoiceService = Depends(get_brand_voice_service),
) -> BrandVoiceEvaluateResponse:
    try:
        return await service.evaluate(request)
    except InvalidInputError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": e.message, "details": e.details},
        )
