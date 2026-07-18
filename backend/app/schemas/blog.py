from typing import Literal

from pydantic import BaseModel, Field


class BlogCreate(BaseModel):
    title: str = Field(min_length=1)
    seo_title: str | None = None
    meta_description: str | None = None
    content: str = Field(min_length=1)
    keywords: str | None = None
    status: Literal["draft", "published"] = "draft"
    project_id: str = "default"
    generation_run_id: str | None = None


class BlogUpdate(BaseModel):
    title: str | None = None
    seo_title: str | None = None
    meta_description: str | None = None
    content: str | None = None
    keywords: str | None = None
    status: Literal["draft", "published"] | None = None
    project_id: str | None = None
    generation_run_id: str | None = None


class BlogResponse(BaseModel):
    id: int
    title: str
    seo_title: str | None
    meta_description: str | None
    content: str
    keywords: str | None
    status: str
    project_id: str = "default"
    generation_run_id: str | None = None
    approved_by: str | None = None
    approved_at: str | None = None
    created_at: str
    updated_at: str
