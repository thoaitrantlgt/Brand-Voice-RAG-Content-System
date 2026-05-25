"""
exceptions.py — Domain Custom Exceptions
SRP: Mỗi exception class đại diện cho đúng 1 loại lỗi nghiệp vụ.
Không dùng Exception gốc rải rác trong code — tập trung tại đây.
"""


class AppBaseException(Exception):
    """Base exception cho toàn bộ ứng dụng."""
    def __init__(self, message: str, details: dict | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


# === Agent / Crew Errors ===

class AgentExecutionError(AppBaseException):
    """Raise khi một Agent CrewAI thất bại trong quá trình chạy task."""


class CrewOrchestrationError(AppBaseException):
    """Raise khi luồng Crew không thể khởi động hoặc bị gián đoạn."""


# === LLM / AI Provider Errors ===

class LLMProviderError(AppBaseException):
    """Raise khi AI provider trả về lỗi (rate limit, auth, network)."""


class UnsupportedProviderError(AppBaseException):
    """Raise khi yêu cầu dùng một AI provider chưa được implement."""


# === Tool Errors ===

class ToolExecutionError(AppBaseException):
    """Raise khi một custom tool của agent gặp lỗi khi thực thi."""


class SearchToolError(ToolExecutionError):
    """Raise khi công cụ tìm kiếm (Tavily/Serper) thất bại."""


# === Schema / Validation Errors ===

class InvalidInputError(AppBaseException):
    """Raise khi dữ liệu đầu vào từ API không hợp lệ về nghiệp vụ."""


# === Content Errors ===

class ContentGenerationError(AppBaseException):
    """Raise khi pipeline tạo nội dung không hoàn tất được output."""
