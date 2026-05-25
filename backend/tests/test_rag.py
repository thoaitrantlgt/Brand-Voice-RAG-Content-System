"""
tests/test_rag.py — Unit Tests cho RAG Pipeline (Phase 2)
Dùng mock để test mà không cần ChromaDB thật hay API keys.
"""
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import Settings
from app.core.interfaces import ProcessedDocument, DocumentChunk
from app.rag.retrieval_engine import RetrievalEngine
from app.services.document_service import DocumentService


@pytest.fixture
def mock_settings():
    return Settings(
        DEBUG=True,
        GOOGLE_API_KEY="test",
        CHUNK_SIZE=500,
        CHUNK_OVERLAP=50,
        RETRIEVAL_TOP_K=3,
    )


@pytest.fixture
def mock_vector_store():
    """Mock IVectorStore — không cần ChromaDB thật."""
    store = MagicMock()
    store.count.return_value = 10
    store.query.return_value = [
        {
            "text": "Đây là nội dung tài liệu tham khảo test.",
            "metadata": {"filename": "test.pdf", "chunk_index": "0", "document_id": "doc-1"},
            "distance": 0.15,
        }
    ]
    store.delete_document.return_value = 5
    return store


@pytest.fixture
def mock_processor():
    """Mock IDocumentProcessor — không đọc file thật."""
    processor = MagicMock()
    processor.supported_extensions.return_value = ["pdf", "txt", "md", "docx"]
    processor.process.return_value = ProcessedDocument(
        document_id="test-doc-id",
        filename="test.pdf",
        total_chunks=3,
        chunks=[
            DocumentChunk(
                text=f"Chunk {i} content",
                metadata={"filename": "test.pdf", "chunk_index": i, "document_id": "test-doc-id"},
                chunk_index=i,
            )
            for i in range(3)
        ],
        source_metadata={"extension": "pdf"},
    )
    return processor


class TestRetrievalEngine:
    def test_retrieve_returns_results(self, mock_vector_store, mock_settings):
        engine = RetrievalEngine(mock_vector_store, mock_settings)
        results = engine.retrieve("test query")
        assert len(results) > 0
        assert "text" in results[0]
        mock_vector_store.query.assert_called_once()

    def test_retrieve_as_context_format(self, mock_vector_store, mock_settings):
        engine = RetrievalEngine(mock_vector_store, mock_settings)
        context = engine.retrieve_as_context("test query")
        assert "Tài liệu tham khảo" in context
        assert "test.pdf" in context

    def test_retrieve_empty_store(self, mock_settings):
        store = MagicMock()
        store.query.return_value = []
        engine = RetrievalEngine(store, mock_settings)
        context = engine.retrieve_as_context("no results query")
        assert "Không tìm thấy" in context


class TestDocumentService:
    @pytest.mark.asyncio
    async def test_upload_and_index(
        self,
        mock_processor,
        mock_vector_store,
        mock_settings,
        tmp_path,
    ):
        # Tạo file test tạm
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")

        service = DocumentService(mock_processor, mock_vector_store, mock_settings)
        result = await service.upload_and_index(test_file, "test.pdf")

        assert result.filename == "test.pdf"
        assert result.total_chunks == 3
        assert result.document_id is not None
        mock_vector_store.add_documents.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_extension_raises(
        self,
        mock_processor,
        mock_vector_store,
        mock_settings,
        tmp_path,
    ):
        from app.core.exceptions import InvalidInputError

        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"binary content")

        service = DocumentService(mock_processor, mock_vector_store, mock_settings)
        with pytest.raises(InvalidInputError):
            await service.upload_and_index(test_file, "test.exe")

    @pytest.mark.asyncio
    async def test_list_documents(
        self,
        mock_processor,
        mock_vector_store,
        mock_settings,
    ):
        service = DocumentService(mock_processor, mock_vector_store, mock_settings)
        result = await service.list_documents()
        assert result.total_documents == 0  # Chưa upload gì

    @pytest.mark.asyncio
    async def test_search(
        self,
        mock_processor,
        mock_vector_store,
        mock_settings,
    ):
        service = DocumentService(mock_processor, mock_vector_store, mock_settings)
        result = await service.search("test query", top_k=3)
        assert result.query == "test query"
        assert len(result.results) == 1
        assert result.results[0].relevance_score > 0
