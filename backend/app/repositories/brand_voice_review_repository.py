import json
import sqlite3

from app.schemas.document import (
    BrandVoiceEvaluateResponse,
    BrandVoiceReviewCreate,
    BrandVoiceReviewResponse,
)


class BrandVoiceReviewRepository:
    """SQLite persistence for brand voice audit and human feedback records."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(
        self,
        review: BrandVoiceReviewCreate,
        evaluation: BrandVoiceEvaluateResponse,
    ) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO brand_voice_reviews (
                profile_id, blog_id, channel, content_type, persona_name,
                content_preview, automated_score, evaluation_json,
                human_score, human_notes, approved, reviewer
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evaluation.profile_id,
                review.blog_id,
                review.channel,
                review.content_type,
                review.persona_name,
                self._preview(review.content),
                evaluation.overall_score,
                evaluation.model_dump_json(),
                review.human_score,
                review.human_notes,
                1 if review.approved else 0,
                review.reviewer,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_by_id(self, review_id: int) -> BrandVoiceReviewResponse | None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM brand_voice_reviews WHERE id = ?", (review_id,))
        row = cursor.fetchone()
        return self._to_response(dict(row)) if row else None

    def list_all(
        self,
        profile_id: str | None = None,
        limit: int = 50,
    ) -> list[BrandVoiceReviewResponse]:
        cursor = self.conn.cursor()
        limit = max(1, min(limit, 200))
        if profile_id:
            cursor.execute(
                """
                SELECT * FROM brand_voice_reviews
                WHERE profile_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (profile_id, limit),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM brand_voice_reviews
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            )
        return [self._to_response(dict(row)) for row in cursor.fetchall()]

    def _to_response(self, row: dict) -> BrandVoiceReviewResponse:
        evaluation = BrandVoiceEvaluateResponse(**json.loads(row["evaluation_json"]))
        return BrandVoiceReviewResponse(
            id=row["id"],
            profile_id=row["profile_id"],
            blog_id=row["blog_id"],
            channel=row["channel"],
            content_type=row["content_type"],
            persona_name=row["persona_name"],
            content_preview=row["content_preview"],
            automated_score=row["automated_score"],
            evaluation=evaluation,
            human_score=row["human_score"],
            human_notes=row["human_notes"],
            approved=bool(row["approved"]),
            reviewer=row["reviewer"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _preview(content: str) -> str:
        return " ".join(content.split())[:500]
