"""
config.py — Application Settings
SRP: Module này chỉ chịu trách nhiệm quản lý cấu hình tập trung.
Tất cả giá trị env var được đọc 1 lần qua đây, không rải rác trong code.
"""
from enum import Enum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class AIProvider(str, Enum):
    """OCP: Thêm provider mới chỉ cần thêm enum — không sửa code gọi."""
    OPENAI = "openai"
    GOOGLE = "google"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    HUGGINGFACE = "huggingface"  # Phase 2: Local HuggingFace models


class EmbeddingProvider(str, Enum):
    """Provider cho Embedding models dùng trong RAG."""
    GOOGLE = "google"              # text-embedding-004
    OPENAI = "openai"              # text-embedding-3-small
    HUGGINGFACE = "huggingface"    # sentence-transformers (local, free)


class RunMode(str, Enum):
    CLOUD = "cloud"
    LOCAL = "local"


class Settings(BaseSettings):
    """
    Cấu hình ứng dụng được load từ file .env.
    Dùng pydantic-settings để validate kiểu dữ liệu tự động.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # === App ===
    APP_NAME: str = "AI Content OS"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # === AI Mode ===
    RUN_MODE: RunMode = RunMode.CLOUD
    AI_PROVIDER: AIProvider = AIProvider.GOOGLE

    # === API Keys (Cloud) ===
    GOOGLE_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    OPENAI_API_BASE: str | None = None
    ANTHROPIC_API_KEY: str = ""

    # === Model Names ===
    PLANNER_MODEL: str = "gemini-1.5-flash"
    WRITER_MODEL: str = "gemini-1.5-pro"
    EDITOR_MODEL: str = "gemini-1.5-flash"

    # === Local Inference (Ollama / vLLM) ===
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    LOCAL_MODEL_NAME: str = "llama3"

    # === HuggingFace (Phase 2) ===
    HUGGINGFACE_API_KEY: str = ""             # HF Inference API key
    HUGGINGFACE_MODEL_ID: str = "mistralai/Mistral-7B-Instruct-v0.3"

    # === Search Tools ===
    TAVILY_API_KEY: str = ""
    SERPER_API_KEY: str = ""

    # === RAG — Embeddings (Phase 2) ===
    EMBEDDING_PROVIDER: EmbeddingProvider = EmbeddingProvider.HUGGINGFACE
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"  # default: free local
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    GOOGLE_EMBEDDING_MODEL: str = "models/text-embedding-004"

    # === RAG — ChromaDB (Phase 2) ===
    CHROMA_PERSIST_DIR: str = "./data/chroma"
    CHROMA_COLLECTION_NAME: str = "knowledge_hub"

    # === RAG — Chunking (Phase 2) ===
    CHUNK_SIZE: int = 1000           # Số ký tự mỗi chunk
    CHUNK_OVERLAP: int = 200         # Overlap giữa các chunk
    RETRIEVAL_TOP_K: int = 5         # Số chunk trả về khi search

    # === File Upload (Phase 2) ===
    UPLOAD_DIR: str = "./data/uploads"
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: list[str] = ["pdf", "txt", "md", "docx"]

    # === Corporate Style Guide ===
    STYLE_GUIDE_PATH: str = "./config/corporate_style_guide.json"
    BRAND_VOICE_PROFILE_PATH: str = "./config/brand_voice_profile.json"
    BRAND_VOICE_DATASET_DIR: str = "./data/brand_voice"

    # === Server ===
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    """
    Factory function — trả về singleton Settings.
    Dùng lru_cache để không đọc lại .env nhiều lần.
    Dễ mock trong tests (override dependency).
    """
    return Settings()
