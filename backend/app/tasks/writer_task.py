"""
tasks/writer_task.py — Writer Task Definition
SRP: Chỉ định nghĩa nhiệm vụ viết bài cho Writer Agent.
"""
from crewai import Agent, Task

from app.core.interfaces import ITask
from app.core.logging import logger


class WriterTask(ITask):
    """
    Task yêu cầu Writer Agent viết bài blog đầy đủ dựa trên tiêu đề và outline.
    """

    def __init__(self, context_tasks: list[Task] | None = None) -> None:
        self._context_tasks = context_tasks or []

    def build(self, agent: Agent) -> Task:
        logger.debug("Building WriterTask")

        return Task(
            description=(
                "/nothink\n"
                "Viết bài blog cho tiêu đề: **{selected_title}**\n"
                "Từ khóa: **{keywords}**\n"
                "Outline: {outline}\n\n"
                "Nhiệm vụ: Chỉ viết nội dung bài blog bằng Markdown, bắt đầu bằng '# {selected_title}'.\n"
                "- Viết bài hoàn chỉnh bằng tiếng Việt.\n"
                "- KHÔNG trả về JSON, chỉ trả về nội dung bài viết.\n"
                "- Các phần: H2, H3 rõ ràng.\n"
            ),
            expected_output=(
                "Nội dung bài viết blog đầy đủ định dạng Markdown, bắt đầu bằng thẻ H1."
            ),
            agent=agent,
            context=self._context_tasks,
        )
