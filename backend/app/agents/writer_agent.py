"""
agents/writer_agent.py — Writer Agent (Expert Copywriter)
SRP: Agent này chỉ chịu trách nhiệm viết nội dung bài blog chi tiết.
"""
from crewai import Agent

from app.core.interfaces import IAgent
from app.core.config import Settings
from app.core.logging import logger
from app.agents.llm_factory import LLMFactory


class WriterAgent(IAgent):
    """
    Expert Copywriter Agent — Nhận tiêu đề từ Planner và viết bài
    chi tiết, chất lượng cao dựa trên RAG context (Phase 2).
    """

    def __init__(self, settings: Settings, tools: list | None = None) -> None:
        self._settings = settings
        self._tools = tools or []
        self._llm_factory = LLMFactory(settings)

    def build(self) -> Agent:
        logger.info("Building WriterAgent | model={}", self._settings.WRITER_MODEL)

        llm = self._llm_factory.create(self._settings.WRITER_MODEL)

        return Agent(
            role="Content Writer",
            goal="Generates the blog content.",
            backstory=(
                "/nothink\n"
                "You're a skilled content writer. You are capable of transforming "
                "an outline into a comprehensive, engaging, and well-structured "
                "blog post. You adapt your writing style to match the target audience."
            ),
            tools=self._tools,
            llm=llm,
            verbose=self._settings.DEBUG,
            allow_delegation=False,
            max_iter=3,           # Giới hạn số lần lặp — 1.7B model không cần nhiều
            max_retry_limit=1,    # Chỉ retry 1 lần khi fail
        )
