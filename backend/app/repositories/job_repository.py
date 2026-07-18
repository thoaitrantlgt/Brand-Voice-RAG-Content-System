import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from app.db.database import get_connection, get_db_path


class JobRepository:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or get_db_path()

    @staticmethod
    def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["payload"] = json.loads(item.pop("payload_json"))
        item["result"] = json.loads(item.pop("result_json")) if item["result_json"] else None
        item["error"] = json.loads(item.pop("error_json")) if item["error_json"] else None
        return item

    def enqueue(
        self,
        project_id: str,
        job_type: str,
        payload: dict[str, Any],
        created_by: str,
        *,
        idempotency_key: str | None = None,
        max_attempts: int = 2,
    ) -> dict[str, Any]:
        with get_connection(self.db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO projects(project_id, name) VALUES (?, ?)",
                (project_id, project_id),
            )
            if idempotency_key:
                existing = conn.execute(
                    "SELECT * FROM jobs WHERE project_id = ? AND idempotency_key = ?",
                    (project_id, idempotency_key),
                ).fetchone()
                if existing:
                    return self._decode(existing)  # type: ignore[return-value]
            job_id = f"job_{uuid.uuid4().hex[:16]}"
            conn.execute(
                """
                INSERT INTO jobs(
                    job_id, project_id, job_type, payload_json, created_by,
                    idempotency_key, max_attempts
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    project_id,
                    job_type,
                    json.dumps(payload, ensure_ascii=False),
                    created_by,
                    idempotency_key,
                    max_attempts,
                ),
            )
            conn.commit()
        return self.get(job_id)  # type: ignore[return-value]

    def get(self, job_id: str) -> dict[str, Any] | None:
        with get_connection(self.db_path) as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return self._decode(row)

    def list_running(self) -> list[dict[str, Any]]:
        with get_connection(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM jobs WHERE status = 'running'").fetchall()
        return [self._decode(row) for row in rows]  # type: ignore[misc]

    def claim_next(self) -> dict[str, Any] | None:
        with get_connection(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at, job_id LIMIT 1"
            ).fetchone()
            if row is None:
                conn.commit()
                return None
            conn.execute(
                """
                UPDATE jobs
                SET status = 'running', attempts = attempts + 1,
                    started_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP,
                    error_json = NULL
                WHERE job_id = ? AND status = 'queued'
                """,
                (row["job_id"],),
            )
            conn.commit()
        return self.get(row["job_id"])

    def complete(self, job_id: str, result: dict[str, Any]) -> None:
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE jobs SET status = 'succeeded', result_json = ?, error_json = NULL,
                    completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE job_id = ? AND status = 'running'
                """,
                (json.dumps(result, ensure_ascii=False), job_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("Only running jobs can complete")
            conn.commit()

    def fail(self, job_id: str, error: dict[str, Any]) -> None:
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE jobs SET status = 'failed', error_json = ?,
                    completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE job_id = ? AND status = 'running'
                """,
                (json.dumps(error, ensure_ascii=False), job_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("Only running jobs can fail")
            conn.commit()

    def retry(self, job_id: str) -> None:
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT status, attempts, max_attempts FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if row is None:
                raise ValueError("Job not found")
            if row["status"] != "failed" or row["attempts"] >= row["max_attempts"]:
                raise ValueError("Job is not retryable")
            conn.execute(
                "UPDATE jobs SET status = 'queued', completed_at = NULL, "
                "updated_at = CURRENT_TIMESTAMP WHERE job_id = ?",
                (job_id,),
            )
            conn.commit()

    def recover_running(self) -> int:
        """Recover jobs claimed by a previous worker process before startup."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE jobs SET
                    status = CASE WHEN attempts < max_attempts THEN 'queued' ELSE 'failed' END,
                    error_json = CASE WHEN attempts < max_attempts THEN NULL ELSE ? END,
                    completed_at = CASE WHEN attempts < max_attempts THEN NULL ELSE CURRENT_TIMESTAMP END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE status = 'running'
                """,
                (json.dumps({"message": "Worker stopped before completing the job"}),),
            )
            conn.commit()
            return cursor.rowcount
