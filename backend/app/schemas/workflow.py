from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ProjectCreate(BaseModel):
    project_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]+$")
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class ContentBrief(BaseModel):
    topic: str = Field(min_length=5, max_length=300)
    keywords: list[str] = Field(min_length=1, max_length=10)
    audience: str = Field(min_length=2, max_length=300)
    objective: str = Field(min_length=2, max_length=500)
    category: str | None = Field(default=None, max_length=100)
    must_cover: list[str] = Field(default=[], max_length=20)
    must_avoid: list[str] = Field(default=[], max_length=20)
    target_length: int = Field(default=800, ge=300, le=3000)
    profile_id: str | None = None
    use_web_search: bool = False
    primary_keyword: str | None = Field(default=None, max_length=150)
    search_intent: Literal[
        "auto", "informational", "commercial", "navigational", "transactional"
    ] = "auto"
    seo_research_enabled: bool = False

    @field_validator("keywords", "must_cover", "must_avoid")
    @classmethod
    def strip_list_items(cls, values: list[str]) -> list[str]:
        return [item.strip() for item in values if item.strip()]


class OutlineUpdate(BaseModel):
    outline: list[str] = Field(min_length=1, max_length=30)


class ReviewRequest(BaseModel):
    approved: bool
    human_score: int | None = Field(default=None, ge=0, le=100)
    notes: str | None = Field(default=None, max_length=2000)
    edited_content: str | None = None


class ProfileTrainRequest(BaseModel):
    name: str = Field(default="Main", min_length=2, max_length=120)
    company_name: str | None = None
    document_ids: list[str] = Field(default=[])
    min_documents: int = Field(default=5, ge=5, le=30)
    max_documents: int = Field(default=30, ge=5, le=30)


class DocumentApprovalRequest(BaseModel):
    status: Literal["pending", "approved", "rejected"]
    human_rating: int | None = Field(default=None, ge=1, le=5)


class JobEnvelope(BaseModel):
    run_id: str | None = None
    job: dict[str, Any]
