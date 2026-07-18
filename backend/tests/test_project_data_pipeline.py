from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.core.interfaces import DocumentChunk, ProcessedDocument
from app.db.database import init_db
from app.repositories.document_repository import DocumentRepository
from app.services.document_service import DocumentService
from scripts.evaluate_tss_pipeline import SheetRecord, clean_extracted_article, stratified_split


def _records() -> list[SheetRecord]:
    rows = []
    index = 1
    for category in ["A", "B", "C", "D", "E"]:
        for position in range(10):
            rows.append(SheetRecord(index, f"https://example.com/{index}", category, 5 if position < 3 else 2, "", ""))
            index += 1
    return rows


def test_stratified_split_is_reproducible_and_balanced():
    train, test = stratified_split(_records(), train_ratio=0.7, seed=42)

    assert len(train) == 35
    assert len(test) == 15
    assert [row.stt for row in test] == [row.stt for row in stratified_split(_records(), 0.7, 42)[1]]
    assert {category: sum(row.category == category for row in test) for category in "ABCDE"} == {
        category: 3 for category in "ABCDE"
    }
    assert any(row.rating >= 4 for row in test)


def test_clean_extracted_article_removes_navigation_and_demo_suffix():
    title, article = clean_extracted_article(
        "Cach lay hoi Footer Demo - The Sun Symphony",
        "Back\nNavigation\nCach lay hoi\nBreadcrumb\nCach lay hoi\nNoi dung chinh",
    )

    assert title == "Cach lay hoi"
    assert article == "Cach lay hoi\nNoi dung chinh"


@pytest.mark.asyncio
async def test_document_metadata_persists_and_is_project_scoped(tmp_path: Path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    repository = DocumentRepository(db_path)
    processor = MagicMock()
    processor.process.return_value = ProcessedDocument(
        document_id="ignored",
        filename="source.md",
        total_chunks=1,
        chunks=[DocumentChunk(text="source", metadata={"document_id": "ignored"}, chunk_index=0)],
        source_metadata={"extension": "md"},
    )
    store = MagicMock()
    store.count.return_value = 999
    settings = Settings(GOOGLE_API_KEY="test")
    path = tmp_path / "source.md"
    path.write_text("source", encoding="utf-8")

    service = DocumentService(processor, store, settings, repository=repository)
    result = await service.upload_and_index(
        path, "source.md", project_id="project-a", cluster="knowledge"
    )
    restarted = DocumentService(processor, store, settings, repository=DocumentRepository(db_path))
    listed = await restarted.list_documents(project_id="project-a")

    assert listed.total_documents == 1
    assert listed.total_chunks == 1
    assert listed.documents[0].document_id == result.document_id
    assert listed.documents[0].project_id == "project-a"
    metadata = store.add_documents.call_args.kwargs["metadatas"][0]
    assert metadata["project_id"] == "project-a"
    assert metadata["cluster"] == "knowledge"


def test_document_approval_cannot_cross_project(tmp_path: Path):
    db_path = tmp_path / "approval.db"
    init_db(db_path)
    repository = DocumentRepository(db_path)
    repository.ensure_project("alpha")
    with repository._connect() as conn:
        conn.execute(
            """
            INSERT INTO documents(
                document_id, project_id, filename, extension, purpose, cluster, total_chunks
            ) VALUES ('doc-1', 'alpha', 'sample.md', 'md', 'brand_voice', 'brand_voice', 1)
            """
        )

    assert repository.set_approval("beta", "doc-1", "approved", 5) is False
    assert repository.set_approval("alpha", "doc-1", "approved", 5) is True
    assert repository.get("doc-1")["approval_status"] == "approved"
