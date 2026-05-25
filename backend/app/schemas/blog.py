from pydantic import BaseModel, Field
from datetime import datetime

class BlogCreate(BaseModel):
    title: str = Field(..., description="Tiêu đề bài viết")
    seo_title: str | None = None
    meta_description: str | None = None
    content: str = Field(..., description="Nội dung bài viết (Markdown)")
    keywords: str | None = None
    status: str = Field(default="draft", description="draft hoặc published")

class BlogUpdate(BaseModel):
    title: str | None = None
    seo_title: str | None = None
    meta_description: str | None = None
    content: str | None = None
    keywords: str | None = None
    status: str | None = None

class BlogResponse(BaseModel):
    id: int
    title: str
    seo_title: str | None
    meta_description: str | None
    content: str
    keywords: str | None
    status: str
    created_at: str
    updated_at: str
