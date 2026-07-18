import json
import uuid
from pathlib import Path
from typing import Any

from app.db.database import get_connection, get_db_path


class BrandVoiceProfileRepository:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or get_db_path()

    @staticmethod
    def _decode(row: Any | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["profile"] = json.loads(item.pop("profile_json"))
        item["metrics"] = json.loads(item.pop("metrics_json"))
        item["source_document_ids"] = json.loads(item.pop("source_document_ids_json"))
        item["is_active"] = bool(item["is_active"])
        return item

    def create(
        self,
        project_id: str,
        name: str,
        profile: dict[str, Any],
        source_document_ids: list[str],
        metrics: dict[str, Any] | None = None,
        artifact_path: str | None = None,
    ) -> dict[str, Any]:
        profile_id = f"profile_{uuid.uuid4().hex[:12]}"
        with get_connection(self.db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO projects(project_id, name) VALUES (?, ?)",
                (project_id, project_id),
            )
            version = conn.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM brand_voice_profiles "
                "WHERE project_id = ? AND name = ?",
                (project_id, name),
            ).fetchone()[0]
            conn.execute(
                """
                INSERT INTO brand_voice_profiles(
                    profile_id, project_id, name, version, is_active, status,
                    source_document_ids_json, profile_json, metrics_json, artifact_path
                ) VALUES (?, ?, ?, ?, 0, 'draft', ?, ?, ?, ?)
                """,
                (
                    profile_id,
                    project_id,
                    name,
                    version,
                    json.dumps(source_document_ids, ensure_ascii=False),
                    json.dumps(profile, ensure_ascii=False),
                    json.dumps(metrics or {}, ensure_ascii=False),
                    artifact_path,
                ),
            )
            conn.commit()
        return self.get(project_id, profile_id)  # type: ignore[return-value]

    def get(self, project_id: str, profile_id: str) -> dict[str, Any] | None:
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM brand_voice_profiles WHERE project_id = ? AND profile_id = ?",
                (project_id, profile_id),
            ).fetchone()
        return self._decode(row)

    def list(self, project_id: str) -> list[dict[str, Any]]:
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM brand_voice_profiles WHERE project_id = ? "
                "ORDER BY name, version DESC",
                (project_id,),
            ).fetchall()
        return [self._decode(row) for row in rows]  # type: ignore[misc]

    def get_active(self, project_id: str) -> dict[str, Any] | None:
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM brand_voice_profiles WHERE project_id = ? AND is_active = 1",
                (project_id,),
            ).fetchone()
        return self._decode(row)

    def activate(self, project_id: str, profile_id: str) -> dict[str, Any]:
        with get_connection(self.db_path) as conn:
            target = conn.execute(
                "SELECT profile_id FROM brand_voice_profiles WHERE project_id = ? AND profile_id = ?",
                (project_id, profile_id),
            ).fetchone()
            if target is None:
                raise ValueError("Profile not found in project")
            conn.execute(
                "UPDATE brand_voice_profiles SET is_active = 0, status = 'archived' "
                "WHERE project_id = ?",
                (project_id,),
            )
            conn.execute(
                "UPDATE brand_voice_profiles SET is_active = 1, status = 'active', "
                "activated_at = CURRENT_TIMESTAMP WHERE project_id = ? AND profile_id = ?",
                (project_id, profile_id),
            )
            conn.commit()
        return self.get(project_id, profile_id)  # type: ignore[return-value]

    def update_artifact(
        self,
        project_id: str,
        profile_id: str,
        profile: dict[str, Any],
        artifact_path: str,
    ) -> None:
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE brand_voice_profiles SET profile_json = ?, artifact_path = ? "
                "WHERE project_id = ? AND profile_id = ?",
                (json.dumps(profile, ensure_ascii=False), artifact_path, project_id, profile_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("Profile not found in project")
            conn.commit()
