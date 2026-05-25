"""
tools/rss_reader_tool.py — RSS Feed Reader Tool
SRP: Tool này chỉ đọc RSS feed để lấy bài viết trending.
"""
import feedparser
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from app.core.exceptions import ToolExecutionError
from app.core.logging import logger


class RSSReaderInput(BaseModel):
    """Input schema cho RSS Reader Tool."""
    url: str = Field(description="URL của RSS feed cần đọc.")
    max_items: int = Field(default=10, description="Số bài viết tối đa cần lấy.")


class RSSReaderTool(BaseTool):
    """
    Tool đọc RSS feed và trả về danh sách bài viết trending.
    Dùng để Planner Agent hiểu xu hướng nội dung hiện tại.
    """
    name: str = "rss_feed_reader"
    description: str = (
        "Đọc RSS feed từ URL được cung cấp và trả về danh sách bài viết mới nhất. "
        "Hữu ích để theo dõi xu hướng nội dung và đề tài đang hot trong lĩnh vực."
    )
    args_schema: type[BaseModel] = RSSReaderInput

    def _run(self, url: str, max_items: int = 10) -> str:
        """
        Đọc và parse RSS feed.

        Returns:
            String chứa danh sách bài viết với title và summary.

        Raises:
            ToolExecutionError: Nếu URL không hợp lệ hoặc feed lỗi.
        """
        logger.debug("Reading RSS feed | url={}", url)

        try:
            feed = feedparser.parse(url)
            if feed.bozo and not feed.entries:
                raise ToolExecutionError(
                    f"Không thể parse RSS feed từ URL: {url}",
                    {"url": url, "bozo_exception": str(feed.bozo_exception)},
                )

            items = feed.entries[:max_items]
            if not items:
                return "RSS feed không có bài viết nào."

            results = []
            for i, entry in enumerate(items, 1):
                title = entry.get("title", "Không có tiêu đề")
                summary = entry.get("summary", "Không có tóm tắt")[:300]
                link = entry.get("link", "")
                results.append(f"{i}. **{title}**\n   {summary}\n   URL: {link}")

            return "\n\n".join(results)

        except ToolExecutionError:
            raise
        except Exception as e:
            raise ToolExecutionError(
                f"Lỗi khi đọc RSS feed: {e}",
                {"url": url},
            ) from e
