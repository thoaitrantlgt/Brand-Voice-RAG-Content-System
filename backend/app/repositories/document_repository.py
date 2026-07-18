import json
import sqlite3
from pathlib import Path
from typing import Any

from app.db.database import get_db_path


class DocumentRepository:
    """Persistent document metadata; vector content remains in ChromaDB."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or get_db_path()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_project(self, project_id: str, name: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO projects(project_id, name) VALUES (?, ?)",
                (project_id, name or project_id),
            )

    def create(self, document: dict[str, Any]) -> None:
        self.ensure_project(document["project_id"])
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO documents (
                    document_id, project_id, profile_id, filename, source_url,
                    extension, purpose, cluster, category, human_rating,
                    dataset_split, total_chunks, status, metadata_json, uploaded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document["document_id"], document["project_id"], document.get("profile_id"),
                    document["filename"], document.get("source_url"), document["extension"],
                    document["purpose"], document["cluster"], document.get("category"),
                    document.get("human_rating"), document.get("dataset_split"),
                    document["total_chunks"], document.get("status", "indexed"),
                    json.dumps(document.get("metadata", {}), ensure_ascii=False),
                    document["uploaded_at"],
                ),
            )

    def list(self, project_id: str | None = None, cluster: str | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        if cluster:
            clauses.append("cluster = ?")
            params.append(cluster)
        sql = "SELECT * FROM documents"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY uploaded_at DESC"
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def get(self, document_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE document_id = ?", (document_id,)
            ).fetchone()
        return dict(row) if row else None

    def delete(self, document_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM documents WHERE document_id = ?", (document_id,))
            return cursor.rowcount > 0

    def set_approval(
        self,
        project_id: str,
        document_id: str,
        approval_status: str,
        human_rating: int | None = None,
    ) -> bool:
        if approval_status not in {"pending", "approved", "rejected"}:
            raise ValueError("Invalid document approval status")
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE documents SET approval_status = ?, human_rating = ?
                WHERE project_id = ? AND document_id = ? AND cluster = 'brand_voice'
                """,
                (approval_status, human_rating, project_id, document_id),
            )
            return cursor.rowcount > 0
