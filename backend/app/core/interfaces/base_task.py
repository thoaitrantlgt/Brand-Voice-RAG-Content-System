"""
interfaces/base_task.py — Task Abstract Interface
ISP: Task chỉ cần 1 method build() — không bị ép phải implement logic không liên quan.
"""
from abc import ABC, abstractmethod

from crewai import Agent, Task


class ITask(ABC):
    """
    Interface cho tất cả Task trong pipeline CrewAI.
    Task nhận Agent đã build xong và trả về crewai.Task đã cấu hình.
    """

    @abstractmethod
    def build(self, agent: Agent) -> Task:
        """
        Tạo crewai.Task với description, expected_output, và agent gán vào.

        Args:
            agent: crewai.Agent sẽ thực thi task này.

        Returns:
            crewai.Task đã cấu hình đầy đủ.
        """
        ...
