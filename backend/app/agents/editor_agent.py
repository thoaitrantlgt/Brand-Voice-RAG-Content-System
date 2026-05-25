"""
agents/editor_agent.py — Editor Agent (SEO Specialist)
SRP: Agent này chỉ chịu trách nhiệm tối ưu nội dung theo tiêu chuẩn SEO.
"""
from crewai import Agent

from app.core.interfaces import IAgent
from app.core.config import Settings
from app.core.logging import logger
from app.agents.llm_factory import LLMFactory


class EditorAgent(IAgent):
    """
    SEO Specialist Agent — Biên tập, tối ưu hóa từ khóa và đảm bảo
    bài viết đạt chuẩn SEO On-page trước khi xuất ra output cuối cùng.
    """

    def __init__(self, settings: Settings, tools: list | None = None) -> None:
        self._settings = settings
        self._tools = tools or []
        self._llm_factory = LLMFactory(settings)

    def build(self) -> Agent:
        logger.info("Building EditorAgent | model={}", self._settings.EDITOR_MODEL)

        llm = self._llm_factory.create(self._settings.EDITOR_MODEL)

        return Agent(
            role="Content Editor",
            goal="Refines the content for clarity, engagement, and accuracy.",
            backstory=(
                "/nothink\n"
                "You're a meticulous editor with an eye for detail. You excel at "
                "polishing drafts, improving flow, and ensuring the content aligns "
                "with the brand's voice and quality standards."
            ),
            tools=self._tools,
            llm=llm,
            verbose=self._settings.DEBUG,
            allow_delegation=False,
            max_iter=3,
            max_retry_limit=1,
        )
