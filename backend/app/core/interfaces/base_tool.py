"""
interfaces/base_tool.py — Tool Abstract Interface
ISP: Chỉ định nghĩa method run() — mỗi tool có 1 trách nhiệm duy nhất.
OCP: Thêm tool mới chỉ cần kế thừa ITool, không sửa code đã chạy.
"""
from abc import ABC, abstractmethod
from typing import Any


class ITool(ABC):
    """
    Interface cho tất cả Custom Tool mà Agent sử dụng.
    Tách biệt contract khỏi implementation cụ thể (Tavily, Serper, v.v.).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Tên tool — CrewAI dùng để nhận diện tool trong prompt."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Mô tả chức năng tool — Agent dùng để quyết định khi nào gọi tool."""
        ...

    @abstractmethod
    def run(self, *args: Any, **kwargs: Any) -> str:
        """
        Thực thi tool và trả về kết quả dạng string để Agent xử lý.

        Returns:
            Kết quả dạng string để nhúng vào context của agent.

        Raises:
            ToolExecutionError: Nếu tool thất bại trong quá trình chạy.
        """
        ...
