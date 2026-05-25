"""
interfaces/base_agent.py — Agent Abstract Interface
ISP + DIP: Định nghĩa contract tối giản mà mỗi Agent phải tuân thủ.
Các class cụ thể (PlannerAgent, WriterAgent...) depend vào abstraction này,
không depend vào nhau — giúp dễ mock, test, và swap implementation.
"""
from abc import ABC, abstractmethod

from crewai import Agent


class IAgent(ABC):
    """
    Interface cho tất cả AI Agent trong hệ thống.
    Mỗi agent chỉ phơi ra 1 method duy nhất: build() → trả về crewai.Agent.
    """

    @abstractmethod
    def build(self) -> Agent:
        """
        Khởi tạo và trả về crewai.Agent đã được cấu hình đầy đủ
        (role, goal, backstory, tools, llm).
        """
        ...
