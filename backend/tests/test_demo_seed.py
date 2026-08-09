import json
from pathlib import Path
from unittest.mock import MagicMock

from app.bootstrap.demo_seed import DemoWorkspaceSeeder
from app.core.config import Settings
from app.db.database import init_db
from app.rag.document_processor import LangChainDocumentProcessor
from app.repositories.brand_voice_profile_repository import BrandVoiceProfileRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.project_repository import ProjectRepository


SEED_DIR = Path(__file__).parents[1] / "seed" / "tss"


def test_bundled_tss_seed_contains_ten_unique_samples():
    manifest = json.loads((SEED_DIR / "manifest.json").read_text(encoding="utf-8"))
    samples = manifest["samples"]

    assert len(samples) == 10
    assert len({item["document_id"] for item in samples}) == 10
    assert len({item["filename"] for item in samples}) == 10
    assert all((SEED_DIR / "writing_samples" / item["filename"]).is_file() for item in samples)
    assert (SEED_DIR / manifest["profile"]["file"]).is_file()


def test_demo_seed_is_ready_to_write_and_idempotent(tmp_path):
    db_path = tmp_path / "blog_os.db"
    init_db(db_path)
    settings = Settings(
        DEMO_SEED_ENABLED=True,
        DEMO_SEED_DIR=str(SEED_DIR),
        CHUNK_SIZE=1000,
        CHUNK_OVERLAP=200,
    )
    vector_store = MagicMock()
    seeder = DemoWorkspaceSeeder(
        settings,
        db_path=db_path,
        processor=LangChainDocumentProcessor(settings),
        vector_store=vector_store,
    )

    first = seeder.run()
    add_call_count = vector_store.add_documents.call_count
    second = seeder.run()

    documents = DocumentRepository(db_path).list("default", "brand_voice")
    profiles = BrandVoiceProfileRepository(db_path).list("default")
    project = ProjectRepository(db_path).get("default")

    assert first["status"] == "seeded"
    assert first["sample_count"] == 10
    assert first["created_samples"] == 10
    assert first["total_chunks"] > 10
    assert second == {
        "status": "already_seeded",
        "project_id": "default",
        "profile_id": profiles[0]["profile_id"],
        "sample_count": 10,
    }
    assert vector_store.add_documents.call_count == add_call_count == 10
    assert len(documents) == 10
    assert all(item["approval_status"] == "approved" for item in documents)
    assert all(int(item["human_rating"]) >= 4 for item in documents)
    assert len(profiles) == 1
    assert profiles[0]["is_active"] is True
    assert profiles[0]["profile"]["dataset_path"] is None
    assert profiles[0]["profile"]["dpo_dataset_path"] is None
    assert project["name"] == "The Sun Symphony Demo"


def test_demo_seed_preserves_an_existing_active_profile(tmp_path):
    db_path = tmp_path / "existing.db"
    init_db(db_path)
    profiles = BrandVoiceProfileRepository(db_path)
    custom = profiles.create("default", "Customer", {"tone": {"primary": "direct"}}, [])
    profiles.activate("default", custom["profile_id"])
    settings = Settings(
        DEMO_SEED_DIR=str(SEED_DIR),
        CHUNK_SIZE=1000,
        CHUNK_OVERLAP=200,
    )

    DemoWorkspaceSeeder(
        settings,
        db_path=db_path,
        processor=LangChainDocumentProcessor(settings),
        vector_store=MagicMock(),
    ).run()

    stored = profiles.list("default")
    assert profiles.get_active("default")["profile_id"] == custom["profile_id"]
    assert next(item for item in stored if item["name"] == "TSS Demo")["is_active"] is False
