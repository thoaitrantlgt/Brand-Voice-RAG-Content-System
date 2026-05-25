"""
app/main.py — FastAPI Application Entry Point
SRP: Chỉ khởi tạo app và gắn routers — không chứa business logic.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.api.v1.content_router import router as content_router
from app.api.v1.document_router import router as document_router
from app.api.v1.blog_router import router as blog_router
from app.db.database import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup → run → shutdown."""
    setup_logging(debug=settings.DEBUG)
    init_db()  # Khởi tạo SQLite database (tạo bảng nếu chưa có)
    yield
    # Cleanup nếu cần (close connections, v.v.)


def create_app() -> FastAPI:
    """
    Application factory — tạo FastAPI instance đã cấu hình.
    Factory pattern giúp dễ tạo multiple app instances trong tests.
    """
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "AI Content Operating System — Tự động hóa quy trình viết blog "
            "với Multi-Agent AI (Planner → Writer → Editor)."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    app.include_router(content_router, prefix="/api/v1")
    app.include_router(document_router, prefix="/api/v1")   # Phase 2: RAG
    app.include_router(blog_router, prefix="/api/v1")       # Blog Management

    @app.get("/health", tags=["System"])
    async def health_check():
        """Health check endpoint cho monitoring."""
        return {
            "status": "healthy",
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "mode": settings.RUN_MODE,
            "provider": settings.AI_PROVIDER,
            "embedding_provider": settings.EMBEDDING_PROVIDER,   # Phase 2
        }

    return app


app = create_app()
