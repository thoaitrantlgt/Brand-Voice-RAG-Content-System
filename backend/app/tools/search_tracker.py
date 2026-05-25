"""
tools/search_tracker.py — Wrapper theo dõi URL từ web search.
Bọc TavilySearchTool để lưu lại các URL đã tìm kiếm, trả về cho Frontend hiển thị.
"""
from crewai.tools import BaseTool
from pydantic import Field


class TrackingSearchTool(BaseTool):
    """
    Wrapper tool theo dõi search results, lưu URL vào shared list.
    Sử dụng thay vì TavilySearchTool trực tiếp khi cần track links.
    """

    name: str = "web_search"
    description: str = (
        "Tìm kiếm thông tin trên web. Input là chuỗi từ khóa cần tìm. "
        "Trả về danh sách kết quả bao gồm tiêu đề, URL và mô tả ngắn."
    )
    # Shared list — ContentCrew sẽ đọc từ đây sau khi crew finish
    collected_links: list[str] = Field(default_factory=list)
    _inner_tool: object = None

    def __init__(self, inner_tool, **kwargs):
        super().__init__(**kwargs)
        self._inner_tool = inner_tool

    def _run(self, query: str) -> str:
        """Gọi tool gốc, trích xuất URLs và lưu lại."""
        result = self._inner_tool._run(query)

        # Trích xuất URL từ kết quả text (Tavily trả về dạng text có URL)
        import re
        urls = re.findall(r'https?://[^\s\)\]"\']+', str(result))
        for url in urls:
            if url not in self.collected_links:
                self.collected_links.append(url)

        return result
