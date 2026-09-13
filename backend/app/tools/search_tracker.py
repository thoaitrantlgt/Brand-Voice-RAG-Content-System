"""
tools/search_tracker.py — Wrapper theo dõi URL từ web search.
Bọc TavilySearchTool để lưu lại các URL đã tìm kiếm, trả về cho Frontend hiển thị.
"""
import json
import re
from urllib.parse import urlparse

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
    queries: list[str] = Field(default_factory=list)
    collected_results: list[dict[str, str]] = Field(default_factory=list)
    _inner_tool: object = None

    def __init__(self, inner_tool, **kwargs):
        super().__init__(**kwargs)
        self._inner_tool = inner_tool

    def _run(self, query: str) -> str:
        """Gọi tool gốc, trích xuất URLs và lưu lại."""
        normalized_query = query.strip()
        if normalized_query and normalized_query not in self.queries:
            self.queries.append(normalized_query)
        result = self._inner_tool._run(query=query)

        # Trích xuất URL từ kết quả text (Tavily trả về dạng text có URL)
        import re
        urls = re.findall(r'https?://[^\s\)\]"\']+', str(result))
        for url in urls:
            if url not in self.collected_links:
                self.collected_links.append(url)

        known_result_urls = {item["url"] for item in self.collected_results}
        for item in self._structured_results(result):
            url = item["url"]
            if url not in self.collected_links:
                self.collected_links.append(url)
            if url not in known_result_urls:
                self.collected_results.append({"query": normalized_query, **item})
                known_result_urls.add(url)

        return result

    def research_report(self) -> dict[str, list]:
        return {
            "query_variations": list(self.queries),
            "sources": list(self.collected_results),
            "source_urls": list(self.collected_links),
        }

    @staticmethod
    def _structured_results(result: object) -> list[dict[str, str]]:
        payload = result
        if isinstance(result, str):
            try:
                payload = json.loads(result)
            except json.JSONDecodeError:
                payload = None

        rows: list[object] = []
        if isinstance(payload, dict):
            candidate = payload.get("organic") or payload.get("results") or []
            rows = candidate if isinstance(candidate, list) else []
        elif isinstance(payload, list):
            rows = payload

        structured: list[dict[str, str]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            url = str(row.get("link") or row.get("url") or "").strip()
            if not url.startswith(("http://", "https://")):
                continue
            structured.append(
                {
                    "title": str(row.get("title") or "").strip(),
                    "url": url,
                    "snippet": str(row.get("snippet") or row.get("content") or "").strip(),
                    "domain": urlparse(url).netloc.lower(),
                }
            )
        if structured:
            return structured

        return [
            {
                "title": "",
                "url": url.rstrip(".,;:"),
                "snippet": "",
                "domain": urlparse(url.rstrip(".,;:")).netloc.lower(),
            }
            for url in re.findall(r'https?://[^\s\)\]"\']+', str(result))
        ]
