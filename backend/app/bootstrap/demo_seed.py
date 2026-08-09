"""Seed a ready-to-write demo workspace without invoking an LLM."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.core.interfaces import IDocumentProcessor, IVectorStore
from app.core.logging import logger
from app.db.database import get_connection, get_db_path
from app.rag.document_processor import LangChainDocumentProcessor
from app.rag.vector_store import ChromaVectorStore
from app.repositories.brand_voice_profile_repository import BrandVoiceProfileRepository
from app.repositories.document_repository import DocumentRepository


class DemoWorkspaceSeeder:
    """Install bundled samples once while preserving user-managed workspace data."""

    def __init__(
        self,
        settings: Settings,
        *,
        db_path: Path | None = None,
        processor: IDocumentProcessor | None = None,
        vector_store: IVectorStore | None = None,
    ) -> None:
        self.settings = settings
        self.db_path = db_path or get_db_path()
        self.seed_dir = Path(settings.DEMO_SEED_DIR)
        self.documents = DocumentRepository(self.db_path)
        self.profiles = BrandVoiceProfileRepository(self.db_path)
        self._processor = processor
        self._vector_store = vector_store

    def run(self) -> dict[str, Any]:
        manifest = self._load_json(self.seed_dir / "manifest.json")
        project = manifest["project"]
        profile_spec = manifest["profile"]
        project_id = str(project["project_id"])
        seed_id = str(manifest["seed_id"])

        existing = self._existing_seed_profile(project_id, profile_spec["name"], seed_id)
        if existing is not None:
            if self.profiles.get_active(project_id) is None:
                existing = self.profiles.activate(project_id, existing["profile_id"])
            logger.info(
                "Demo workspace already seeded | project={} profile={}",
                project_id,
                existing["profile_id"],
            )
            return {
                "status": "already_seeded",
                "project_id": project_id,
                "profile_id": existing["profile_id"],
                "sample_count": len(existing["source_document_ids"]),
            }

        self._prepare_project(project_id, str(project["name"]), project.get("description"))
        source_document_ids: list[str] = []
        created_samples = 0
        total_chunks = 0

        for sample in manifest["samples"]:
            document_id = str(sample["document_id"])
            source_document_ids.append(document_id)
            current = self.documents.get(document_id)
            if current is not None:
                total_chunks += int(current.get("total_chunks") or 0)
                self.documents.set_approval(
                    project_id, document_id, "approved", int(sample["rating"])
                )
                continue

            sample_path = self._safe_sample_path(str(sample["filename"]))
            processed = self.processor.process(sample_path, document_id)
            metadatas = []
            for chunk in processed.chunks:
                metadata = dict(chunk.metadata)
                metadata.update(
                    {
                        "purpose": "brand_voice",
                        "cluster": "brand_voice",
                        "project_id": project_id,
                        "source_url": str(sample["source_url"]),
                        "category": str(sample["category"]),
                        "dataset_split": str(sample["dataset_split"]),
                        "seed_id": seed_id,
                    }
                )
                metadatas.append(metadata)
            ids = [f"{document_id}_{index}" for index in range(processed.total_chunks)]
            self.vector_store.add_documents(
                [chunk.text for chunk in processed.chunks], metadatas, ids
            )
            self.documents.create(
                {
                    "document_id": document_id,
                    "project_id": project_id,
                    "filename": str(sample["filename"]),
                    "source_url": str(sample["source_url"]),
                    "extension": "md",
                    "purpose": "brand_voice",
                    "cluster": "brand_voice",
                    "category": str(sample["category"]),
                    "human_rating": int(sample["rating"]),
                    "dataset_split": str(sample["dataset_split"]),
                    "total_chunks": processed.total_chunks,
                    "status": "indexed",
                    "metadata": {"seed_id": seed_id},
                    "uploaded_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            self.documents.set_approval(
                project_id, document_id, "approved", int(sample["rating"])
            )
            total_chunks += processed.total_chunks
            created_samples += 1

        profile_path = self.seed_dir / str(profile_spec["file"])
        profile = self._load_json(profile_path)
        profile.update(
            {
                "profile_id": str(profile_spec["profile_key"]),
                "source_document_count": len(source_document_ids),
                "source_documents": [
                    {
                        "document_id": str(sample["document_id"]),
                        "filename": str(sample["filename"]),
                    }
                    for sample in manifest["samples"]
                ],
                "dataset_path": None,
                "dpo_dataset_path": None,
                "indexed_chunks": total_chunks,
            }
        )
        stored = self.profiles.create(
            project_id,
            str(profile_spec["name"]),
            profile,
            source_document_ids,
            metrics={
                "seed_id": seed_id,
                "seed_version": int(manifest["version"]),
                "writing_fingerprint": profile.get("writing_fingerprint", {}),
            },
            artifact_path=str(profile_path),
        )
        if self.profiles.get_active(project_id) is None:
            stored = self.profiles.activate(project_id, stored["profile_id"])

        logger.info(
            "Demo workspace seeded | project={} samples={} chunks={} profile={}",
            project_id,
            len(source_document_ids),
            total_chunks,
            stored["profile_id"],
        )
        return {
            "status": "seeded",
            "project_id": project_id,
            "profile_id": stored["profile_id"],
            "sample_count": len(source_document_ids),
            "created_samples": created_samples,
            "total_chunks": total_chunks,
        }

    @property
    def processor(self) -> IDocumentProcessor:
        if self._processor is None:
            self._processor = LangChainDocumentProcessor(self.settings)
        return self._processor

    @property
    def vector_store(self) -> IVectorStore:
        if self._vector_store is None:
            self._vector_store = ChromaVectorStore(self.settings)
        return self._vector_store

    def _existing_seed_profile(
        self, project_id: str, profile_name: str, seed_id: str
    ) -> dict[str, Any] | None:
        for profile in self.profiles.list(project_id):
            if profile["name"] == profile_name or profile["metrics"].get("seed_id") == seed_id:
                return profile
        return None

    def _prepare_project(self, project_id: str, name: str, description: Any) -> None:
        self.documents.ensure_project(project_id, name)
        with get_connection(self.db_path) as conn:
            conn.execute(
                "UPDATE projects SET name = ?, description = COALESCE(description, ?), "
                "updated_at = CURRENT_TIMESTAMP WHERE project_id = ? "
                "AND name IN ('Default project', ?)",
                (name, description, project_id, project_id),
            )
            conn.commit()

    def _safe_sample_path(self, filename: str) -> Path:
        samples_dir = (self.seed_dir / "writing_samples").resolve()
        candidate = (samples_dir / filename).resolve()
        if candidate.parent != samples_dir or not candidate.is_file():
            raise ValueError(f"Invalid bundled sample path: {filename}")
        return candidate

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        if not path.is_file():
            raise FileNotFoundError(f"Demo seed asset is missing: {path}")
        return json.loads(path.read_text(encoding="utf-8"))
