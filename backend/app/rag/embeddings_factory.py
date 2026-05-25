"""
rag/embeddings_factory.py — Embedding Model Factory
OCP + DIP: Tạo embedding function theo cấu hình.
Hỗ trợ Google, OpenAI (cloud) và HuggingFace/sentence-transformers (local/free).
ChromaDB nhận embedding function trực tiếp — không cần convert thủ công.
"""
from typing import Protocol

import chromadb.utils.embedding_functions as ef

from app.core.config import EmbeddingProvider, Settings
from app.core.exceptions import UnsupportedProviderError
from app.core.logging import logger


class EmbeddingFunction(Protocol):
    """Protocol typing cho ChromaDB EmbeddingFunction."""
    def __call__(self, input: list[str]) -> list[list[float]]: ...


class EmbeddingsFactory:
    """
    Factory tạo ChromaDB-compatible embedding function theo cấu hình.
    Agent và VectorStore không biết embedding model cụ thể là gì (DIP).
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(self) -> EmbeddingFunction:
        """
        Tạo embedding function phù hợp với EMBEDDING_PROVIDER.

        Returns:
            ChromaDB EmbeddingFunction đã cấu hình.

        Raises:
            UnsupportedProviderError: Nếu provider chưa được hỗ trợ.
        """
        provider = self._settings.EMBEDDING_PROVIDER

        if provider == EmbeddingProvider.HUGGINGFACE:
            return self._create_huggingface()
        elif provider == EmbeddingProvider.GOOGLE:
            return self._create_google()
        elif provider == EmbeddingProvider.OPENAI:
            return self._create_openai()
        else:
            raise UnsupportedProviderError(
                f"Embedding provider '{provider}' chưa được hỗ trợ.",
                {"supported": [p.value for p in EmbeddingProvider]},
            )

    def _create_huggingface(self) -> EmbeddingFunction:
        """
        Dùng sentence-transformers — chạy hoàn toàn local, không cần API key.
        Default model: all-MiniLM-L6-v2 (nhỏ, nhanh, chất lượng tốt).
        """
        model = self._settings.EMBEDDING_MODEL
        logger.info("Creating HuggingFace embedding | model={}", model)

        return ef.SentenceTransformerEmbeddingFunction(
            model_name=model,
            device="cpu",   # Đổi thành "cuda" nếu có GPU
        )

    def _create_google(self) -> EmbeddingFunction:
        """Google text-embedding-004 — cần GOOGLE_API_KEY."""
        model = self._settings.GOOGLE_EMBEDDING_MODEL
        logger.info("Creating Google embedding | model={}", model)

        return ef.GoogleGenerativeAiEmbeddingFunction(
            api_key=self._settings.GOOGLE_API_KEY,
            model_name=model,
        )

    def _create_openai(self) -> EmbeddingFunction:
        """OpenAI text-embedding-3-small — cần OPENAI_API_KEY."""
        model = self._settings.OPENAI_EMBEDDING_MODEL
        logger.info("Creating OpenAI embedding | model={}", model)

        return ef.OpenAIEmbeddingFunction(
            api_key=self._settings.OPENAI_API_KEY,
            model_name=model,
        )
