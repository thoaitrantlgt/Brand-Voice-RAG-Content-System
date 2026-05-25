"""
tools/web_search_tool.py — Web Search Tool (Tavily / Serper)
SRP: Tool này chỉ chịu trách nhiệm tìm kiếm web.
OCP: Implement ITool — thêm search provider mới không phá vỡ code gọi tool.
"""
from typing import Any

from crewai_tools import SerperDevTool

from app.core.config import Settings
from app.core.exceptions import SearchToolError
from app.core.logging import logger


def create_web_search_tool(settings: Settings) -> SerperDevTool:
    """
    Factory function tạo web search tool theo cấu hình.
    Trả về SerperDevTool đã cấu hình để dùng trực tiếp trong CrewAI.

    Raises:
        SearchToolError: Nếu API key chưa được cấu hình.
    """
    if not settings.SERPER_API_KEY:
        raise SearchToolError(
            "SERPER_API_KEY chưa được cấu hình trong .env",
            {"env_var": "SERPER_API_KEY"},
        )

    logger.debug("Creating SerperDevTool tool")
    
    import os
    os.environ["SERPER_API_KEY"] = settings.SERPER_API_KEY
    
    return SerperDevTool(
        n_results=5,
    )
