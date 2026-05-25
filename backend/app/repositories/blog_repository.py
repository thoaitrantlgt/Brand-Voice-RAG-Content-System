import sqlite3
from app.schemas.blog import BlogCreate, BlogUpdate

class BlogRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, blog: BlogCreate) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO blogs (title, seo_title, meta_description, content, keywords, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                blog.title, blog.seo_title, blog.meta_description,
                blog.content, blog.keywords, blog.status
            )
        )
        self.conn.commit()
        return cursor.lastrowid

    def list_all(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM blogs ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]

    def get_by_id(self, blog_id: int):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM blogs WHERE id = ?", (blog_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def update(self, blog_id: int, update_data: BlogUpdate) -> bool:
        update_fields = update_data.model_dump(exclude_unset=True)
        if not update_fields:
            return False

        set_clause = ", ".join([f"{k} = ?" for k in update_fields.keys()])
        set_clause += ", updated_at = CURRENT_TIMESTAMP"
        values = list(update_fields.values())
        values.append(blog_id)

        cursor = self.conn.cursor()
        cursor.execute(f"UPDATE blogs SET {set_clause} WHERE id = ?", values)
        self.conn.commit()
        return cursor.rowcount > 0

    def delete(self, blog_id: int) -> bool:
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM blogs WHERE id = ?", (blog_id,))
        self.conn.commit()
        return cursor.rowcount > 0
