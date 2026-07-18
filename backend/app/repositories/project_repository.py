from pathlib import Path
from typing import Any

from app.db.database import get_connection, get_db_path


class ProjectRepository:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or get_db_path()

    def create(self, project_id: str, name: str, description: str | None = None) -> dict[str, Any]:
        with get_connection(self.db_path) as conn:
            try:
                conn.execute(
                    "INSERT INTO projects(project_id, name, description) VALUES (?, ?, ?)",
                    (project_id, name, description),
                )
                conn.commit()
            except Exception as exc:
                raise ValueError("Project already exists") from exc
        return self.get(project_id)  # type: ignore[return-value]

    def get(self, project_id: str) -> dict[str, Any] | None:
        with get_connection(self.db_path) as conn:
            row = conn.execute("SELECT * FROM projects WHERE project_id = ?", (project_id,)).fetchone()
        return dict(row) if row else None

    def list(self) -> list[dict[str, Any]]:
        with get_connection(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY name, project_id").fetchall()
        return [dict(row) for row in rows]
