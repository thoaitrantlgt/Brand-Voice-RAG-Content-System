import sqlite3

from app.schemas.blog import BlogCreate, BlogUpdate


class BlogRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, blog: BlogCreate) -> int:
        self._validate_publish(blog)
        cursor = self.conn.execute(
            """
            INSERT INTO blogs (
                title, seo_title, meta_description, content, keywords, status,
                project_id, generation_run_id, approved_by, approved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?,
                (SELECT reviewed_by FROM generation_runs WHERE run_id = ?),
                (SELECT reviewed_at FROM generation_runs WHERE run_id = ?))
            """,
            (
                blog.title,
                blog.seo_title,
                blog.meta_description,
                blog.content,
                blog.keywords,
                blog.status,
                blog.project_id,
                blog.generation_run_id,
                blog.generation_run_id,
                blog.generation_run_id,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def list_all(self, project_id: str | None = None):
        if project_id:
            rows = self.conn.execute(
                "SELECT * FROM blogs WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM blogs ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def get_by_id(self, blog_id: int):
        row = self.conn.execute("SELECT * FROM blogs WHERE id = ?", (blog_id,)).fetchone()
        return dict(row) if row else None

    def update(self, blog_id: int, update_data: BlogUpdate) -> bool:
        update_fields = update_data.model_dump(exclude_unset=True)
        if not update_fields:
            return False
        current = self.get_by_id(blog_id)
        if current is None:
            return False
        if current["status"] == "published":
            raise ValueError("Published blogs are immutable")
        if "project_id" in update_fields or "generation_run_id" in update_fields:
            raise ValueError("Blog project and generation run are immutable")
        if update_fields.get("status") == "published":
            raise ValueError("Publish through the approved generation workflow")

        set_clause = ", ".join(f"{key} = ?" for key in update_fields)
        values = [*update_fields.values(), blog_id]
        cursor = self.conn.execute(
            f"UPDATE blogs SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", values
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def delete(self, blog_id: int) -> bool:
        current = self.get_by_id(blog_id)
        if current and current["status"] == "published":
            raise ValueError("Published blogs are immutable")
        cursor = self.conn.execute("DELETE FROM blogs WHERE id = ?", (blog_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def _validate_publish(self, blog: BlogCreate) -> None:
        if blog.status != "published":
            return
        if not blog.generation_run_id:
            raise ValueError("Publishing requires an approved generation run")
        row = self.conn.execute(
            "SELECT * FROM generation_runs WHERE run_id = ?", (blog.generation_run_id,)
        ).fetchone()
        if row is None or row["status"] not in {"approved", "published"}:
            raise ValueError("Publishing requires an approved generation run")
        approved_content = row["edited_content"] or row["final_content"]
        approved_title = row["planned_title"] or "Untitled"
        if (
            blog.project_id != row["project_id"]
            or blog.title != approved_title
            or blog.content != approved_content
        ):
            raise ValueError("Published blog must match the approved generation run")
