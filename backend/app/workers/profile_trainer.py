import json
import shutil
from pathlib import Path
from typing import Any

from app.repositories.brand_voice_profile_repository import BrandVoiceProfileRepository
from app.schemas.document import TrainBrandVoiceRequest


class ProjectProfileTrainer:
    def __init__(self, brand_service: Any, documents: Any, profiles: BrandVoiceProfileRepository):
        self.brand_service = brand_service
        self.documents = documents
        self.profiles = profiles

    async def __call__(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        candidates = self.documents.list(project_id=project_id, cluster="brand_voice")
        eligible = {
            item["document_id"]
            for item in candidates
            if item.get("project_id", project_id) == project_id
            and item.get("cluster", "brand_voice") == "brand_voice"
            and item.get("approval_status") == "approved"
            and int(item.get("human_rating") or 0) >= 4
        }
        requested = list(payload.get("document_ids") or [])
        if requested and any(document_id not in eligible for document_id in requested):
            raise ValueError("Selected documents must be eligible approved brand voice documents")
        selected = requested or sorted(eligible)
        minimum = int(payload.get("min_documents", 5))
        if len(selected) < minimum:
            raise ValueError(
                f"At least {minimum} approved brand voice documents are required; found {len(selected)}"
            )
        result = await self.brand_service.train(
            TrainBrandVoiceRequest(
                company_name=payload.get("company_name"),
                document_ids=selected,
                min_documents=minimum,
                max_documents=int(payload.get("max_documents", 30)),
            )
        )
        profile_path = Path(result.profile_path)
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        stored = self.profiles.create(
            project_id,
            str(payload.get("name") or "Main"),
            profile,
            selected,
            metrics=profile.get("writing_fingerprint", {}),
            artifact_path=None,
        )
        artifact_dir = (
            self.profiles.db_path.parent
            / "brand_voice"
            / "profiles"
            / project_id
            / stored["profile_id"]
        )
        artifact_dir.mkdir(parents=True, exist_ok=False)
        immutable_profile_path = artifact_dir / "profile.json"
        for attribute, filename in (
            ("dataset_path", "sft.jsonl"),
            ("dpo_dataset_path", "dpo.jsonl"),
        ):
            source_value = getattr(result, attribute, None)
            if source_value and Path(source_value).exists():
                destination = artifact_dir / filename
                shutil.copy2(source_value, destination)
                profile[attribute] = str(destination)
        immutable_profile_path.write_text(
            json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self.profiles.update_artifact(
            project_id, stored["profile_id"], profile, str(immutable_profile_path)
        )
        return self.profiles.activate(project_id, stored["profile_id"])
