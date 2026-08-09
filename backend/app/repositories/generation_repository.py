from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from app.db.database import get_connection, get_db_path


class GenerationRunRepository:
    JSON_FIELDS = {
        "brief_json": "brief",
        "outline_json": "outline",
        "quality_report_json": "quality_report",
    }

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or get_db_path()

    @classmethod
    def _decode(cls, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        for source, target in cls.JSON_FIELDS.items():
            item[target] = json.loads(item.pop(source))
        return item

    def create(
        self,
        project_id: str,
        brief: dict[str, Any],
        created_by: str,
        profile_id: str | None = None,
        profile_version: int | None = None,
    ) -> dict[str, Any]:
        run_id = f"run_{uuid.uuid4().hex[:16]}"
        with get_connection(self.db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO projects(project_id, name) VALUES (?, ?)",
                (project_id, project_id),
            )
            conn.execute(
                """
                INSERT INTO generation_runs(
                    run_id, project_id, profile_id, profile_version, brief_json, created_by
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    project_id,
                    profile_id,
                    profile_version,
                    json.dumps(brief, ensure_ascii=False),
                    created_by,
                ),
            )
            conn.commit()
        return self.get(run_id)  # type: ignore[return-value]

    def get(self, run_id: str) -> dict[str, Any] | None:
        with get_connection(self.db_path) as conn:
            row = conn.execute("SELECT * FROM generation_runs WHERE run_id = ?", (run_id,)).fetchone()
            citations = conn.execute(
                "SELECT document_id, chunk_index, source_url, excerpt, relevance_score "
                "FROM generation_citations WHERE run_id = ? ORDER BY id",
                (run_id,),
            ).fetchall()
            retrieval_contexts = conn.execute(
                "SELECT rank, document_id, chunk_index, context_text AS text, relevance_score "
                "FROM generation_retrieval_contexts WHERE run_id = ? ORDER BY rank",
                (run_id,),
            ).fetchall()
            blog = conn.execute(
                "SELECT id FROM blogs WHERE generation_run_id = ?", (run_id,)
            ).fetchone()
        item = self._decode(row)
        if item is not None:
            item["citations"] = [dict(citation) for citation in citations]
            item["retrieval_contexts"] = [dict(context) for context in retrieval_contexts]
            item["blog_id"] = blog["id"] if blog else None
        return item

    def list(self, project_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM generation_runs WHERE project_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
        return [self._decode(row) for row in rows]  # type: ignore[misc]

    def _transition(self, run_id: str, allowed: set[str], status: str) -> None:
        with get_connection(self.db_path) as conn:
            row = conn.execute("SELECT status FROM generation_runs WHERE run_id = ?", (run_id,)).fetchone()
            if row is None or row["status"] not in allowed:
                raise ValueError(f"Cannot transition generation run to {status}")
            conn.execute(
                "UPDATE generation_runs SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE run_id = ?",
                (status, run_id),
            )
            conn.commit()

    def set_outline(self, run_id: str, outline: list[str]) -> dict[str, Any]:
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE generation_runs SET outline_json = ?, status = 'outline_ready',
                    updated_at = CURRENT_TIMESTAMP
                WHERE run_id = ? AND status IN ('planning', 'outline_ready')
                """,
                (json.dumps(outline, ensure_ascii=False), run_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("Run is not accepting an outline")
            conn.commit()
        return self.get(run_id)  # type: ignore[return-value]

    def set_plan(
        self, run_id: str, title: str, seo_title: str, outline: list[str]
    ) -> dict[str, Any]:
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE generation_runs SET planned_title = ?, planned_seo_title = ?,
                    outline_json = ?, status = 'outline_ready', updated_at = CURRENT_TIMESTAMP
                WHERE run_id = ? AND status = 'planning'
                """,
                (title, seo_title, json.dumps(outline, ensure_ascii=False), run_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("Run is not accepting a plan")
            conn.commit()
        return self.get(run_id)  # type: ignore[return-value]

    def begin_generation(self, run_id: str) -> None:
        self._transition(run_id, {"outline_ready", "failed"}, "generating")

    def fail_generation(self, run_id: str) -> None:
        with get_connection(self.db_path) as conn:
            conn.execute(
                "UPDATE generation_runs SET status = 'failed', updated_at = CURRENT_TIMESTAMP "
                "WHERE run_id = ? AND status = 'generating'",
                (run_id,),
            )
            conn.commit()

    def record_attempt(
        self,
        run_id: str,
        content: str,
        quality_report: dict[str, Any],
        model_name: str,
        prompt_version: str = "internal-v1",
        duration_seconds: float | None = None,
    ) -> int:
        with get_connection(self.db_path) as conn:
            status = conn.execute(
                "SELECT status FROM generation_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if status is None or status["status"] != "generating":
                raise ValueError("Run is not generating")
            attempt_number = conn.execute(
                "SELECT COALESCE(MAX(attempt_number), 0) + 1 FROM generation_attempts WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
            conn.execute(
                """
                INSERT INTO generation_attempts(
                    run_id, attempt_number, content, quality_report_json,
                    model_name, prompt_version, duration_seconds
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    attempt_number,
                    content,
                    json.dumps(quality_report, ensure_ascii=False),
                    model_name,
                    prompt_version,
                    duration_seconds,
                ),
            )
            conn.commit()
        return attempt_number

    def replace_citations(self, run_id: str, citations: list[dict[str, Any]]) -> None:
        with get_connection(self.db_path) as conn:
            conn.execute("DELETE FROM generation_citations WHERE run_id = ?", (run_id,))
            conn.executemany(
                """
                INSERT INTO generation_citations(
                    run_id, document_id, chunk_index, source_url, excerpt, relevance_score
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        item["document_id"],
                        item.get("chunk_index"),
                        item.get("source_url"),
                        item.get("excerpt", ""),
                        item.get("relevance_score"),
                    )
                    for item in citations
                ],
            )
            conn.commit()

    def replace_retrieval_contexts(
        self, run_id: str, contexts: list[dict[str, Any]]
    ) -> None:
        with get_connection(self.db_path) as conn:
            conn.execute("DELETE FROM generation_retrieval_contexts WHERE run_id = ?", (run_id,))
            conn.executemany(
                """
                INSERT INTO generation_retrieval_contexts(
                    run_id, rank, document_id, chunk_index, context_text, relevance_score
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        int(item.get("rank", index)),
                        item.get("document_id"),
                        item.get("chunk_index"),
                        str(item.get("text", "")),
                        item.get("relevance_score"),
                    )
                    for index, item in enumerate(contexts, 1)
                    if str(item.get("text", "")).strip()
                ],
            )
            conn.commit()

    def finalize(
        self,
        run_id: str,
        content: str,
        quality_report: dict[str, Any],
        rewrite_count: int,
        title_tag: str | None = None,
        meta_description: str | None = None,
    ) -> dict[str, Any]:
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE generation_runs SET final_content = ?, quality_report_json = ?,
                    rewrite_count = ?, title_tag = ?, meta_description = ?,
                    status = 'needs_review', updated_at = CURRENT_TIMESTAMP
                WHERE run_id = ? AND status = 'generating'
                """,
                (
                    content,
                    json.dumps(quality_report, ensure_ascii=False),
                    rewrite_count,
                    title_tag,
                    meta_description,
                    run_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("Run is not generating")
            conn.commit()
        return self.get(run_id)  # type: ignore[return-value]

    def review(
        self,
        run_id: str,
        reviewer: str,
        approved: bool,
        human_score: int | None = None,
        notes: str | None = None,
        edited_content: str | None = None,
    ) -> dict[str, Any]:
        status = "approved" if approved else "rejected"
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE generation_runs SET status = ?, reviewed_by = ?, human_score = ?,
                    review_notes = ?, edited_content = ?,
                    reviewed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE run_id = ? AND status = 'needs_review'
                """,
                (status, reviewer, human_score, notes, edited_content, run_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("Only runs needing review can be reviewed")
            conn.commit()
        return self.get(run_id)  # type: ignore[return-value]

    def publish(self, run_id: str) -> dict[str, Any]:
        with get_connection(self.db_path) as conn:
            run = conn.execute(
                "SELECT * FROM generation_runs WHERE run_id = ? AND status = 'approved'",
                (run_id,),
            ).fetchone()
            if run is None:
                raise ValueError("Generation run must be approved before publishing")
            content = run["edited_content"] or run["final_content"]
            if not content:
                raise ValueError("Approved generation run has no content")
            existing = conn.execute(
                "SELECT id FROM blogs WHERE generation_run_id = ?", (run_id,)
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO blogs(
                        title, seo_title, meta_description, content, keywords, status,
                        project_id, generation_run_id, approved_by, approved_at
                    ) VALUES (?, ?, ?, ?, ?, 'published', ?, ?, ?, ?)
                    """,
                    (
                        run["planned_title"] or "Untitled",
                        run["planned_seo_title"] or run["title_tag"],
                        run["meta_description"],
                        content,
                        ", ".join(json.loads(run["brief_json"]).get("keywords", [])),
                        run["project_id"],
                        run_id,
                        run["reviewed_by"],
                        run["reviewed_at"],
                    ),
                )
            conn.execute(
                "UPDATE generation_runs SET status = 'published', updated_at = CURRENT_TIMESTAMP "
                "WHERE run_id = ?",
                (run_id,),
            )
            conn.commit()
        return self.get(run_id)  # type: ignore[return-value]
