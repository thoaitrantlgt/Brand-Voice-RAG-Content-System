"""
interfaces/base_crew.py — Crew Abstract Interface
OCP + DIP: Crew là orchestrator — depend vào IAgent và ITask abstractions,
không depend vào implementation cụ thể nào.
"""
from abc import ABC, abstractmethod
from typing import Any


class ICrew(ABC):
    """
    Interface cho CrewAI Crew orchestration.
    Mỗi Crew tập hợp các Agent + Task và chạy pipeline.
    """

    @abstractmethod
    def run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """
        Khởi động pipeline của Crew với các input được cung cấp.

        Args:
            inputs: Dict chứa các thông số đầu vào (keywords, selected_title, outline, v.v.).

        Returns:
            Dict chứa kết quả đầu ra từ pipeline.

        Raises:
            CrewOrchestrationError: Nếu pipeline bị gián đoạn.
        """
        ...
