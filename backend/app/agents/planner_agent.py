"""
agents/planner_agent.py — Planner Agent (Content Strategist)
SRP: Agent này chỉ chịu trách nhiệm phân tích từ khóa và lập dàn ý.
LSP: Implement đúng contract IAgent.build() — có thể thay thế IAgent bất kỳ lúc nào.
"""
from crewai import Agent

from app.core.interfaces import IAgent
from app.core.config import Settings
from app.core.logging import logger
from app.agents.llm_factory import LLMFactory


class PlannerAgent(IAgent):
    """
    Content Strategist Agent — Phân tích từ khóa, nghiên cứu thị trường,
    và tạo danh sách tiêu đề bài viết tiềm năng.

    Tools: keyword_research, web_search, rss_reader.
    """

    def __init__(self, settings: Settings, tools: list | None = None) -> None:
        """
        DIP: Nhận Settings và tools từ bên ngoài thay vì tự khởi tạo.

        Args:
            settings: App settings để khởi tạo LLM.
            tools: Danh sách CrewAI tools được inject vào agent.
        """
        self._settings = settings
        self._tools = tools or []
        self._llm_factory = LLMFactory(settings)

    def build(self) -> Agent:
        """Tạo và trả về crewai.Agent đã cấu hình cho Planner."""
        logger.info("Building PlannerAgent | model={}", self._settings.PLANNER_MODEL)

        llm = self._llm_factory.create(self._settings.PLANNER_MODEL)

        return Agent(
            role="Content Planner",
            goal="Structures and strategizes blog content based on the input query.",
            backstory=(
                "/nothink\n"
                "You're an expert content strategist. You excel at understanding "
                "a topic, identifying the core message, and organizing the content "
                "into a clear, logical, and engaging outline."
            ),
            tools=self._tools,
            llm=llm,
            verbose=self._settings.DEBUG,
            allow_delegation=False,
            max_iter=3,
            max_retry_limit=1,
        )
