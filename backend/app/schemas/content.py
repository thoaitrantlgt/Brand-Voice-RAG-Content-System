"""Pydantic schemas for the Content API."""
from pydantic import BaseModel, Field


class GenerateTitlesRequest(BaseModel):
    """Request for Planner Agent draft generation."""
    keywords: list[str] = Field(
        min_length=1,
        max_length=10,
        description="Keywords to research and turn into a draft outline.",
        examples=[["AI writing tool", "content automation"]],
    )
    use_web_search: bool = Field(
        default=False,
        description="Enable web search for current information.",
    )


class GenerateContentRequest(BaseModel):
    """Request for Writer + Editor article generation."""
    keywords: list[str] = Field(
        min_length=1,
        description="Main keywords to optimize in the article.",
    )
    selected_title: str = Field(
        min_length=10,
        max_length=200,
        description="Title approved by the user after the Planner step.",
        examples=["10 ways to use AI to write blog posts faster"],
    )
    outline: list[str] = Field(
        default=[],
        description="Editable outline approved by the user.",
    )
    use_web_search: bool = Field(
        default=False,
        description="Enable web search for the Writer Agent.",
    )


class RewriteRequest(BaseModel):
    """Request to rewrite selected text based on user feedback."""
    original_text: str = Field(min_length=1)
    feedback: str = Field(min_length=1)


class PostTitleItem(BaseModel):
    """One editable draft plan returned by Planner Agent."""
    keyword: str
    title: str
    seo_title: str
    outline: list[str]


class GenerateTitlesResponse(BaseModel):
    """Planner API response."""
    titles: list[PostTitleItem]
    search_links: list[str] = Field(default=[])
    status: str = "success"


class GenerateContentResponse(BaseModel):
    """Content generation API response."""
    optimized_content: str = Field(description="SEO-optimized article in Markdown.")
    title_tag: str = Field(description="SEO title tag.")
    meta_description: str = Field(description="Meta description.")
    style_report: dict = Field(default={}, description="Corporate style guide enforcement report.")
    status: str = "success"


class RewriteResponse(BaseModel):
    """Inline rewrite API response."""
    rewritten_text: str = Field(description="Rewritten text.")
    style_report: dict = Field(default={}, description="Corporate style guide enforcement report.")
    status: str = "success"


class ErrorResponse(BaseModel):
    """Normalized error response."""
    error: str
    details: dict = {}
    status: str = "error"
