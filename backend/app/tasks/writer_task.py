"""
tasks/writer_task.py - Writer Task Definition.
"""
from crewai import Agent, Task

from app.core.interfaces import ITask
from app.core.logging import logger


class WriterTask(ITask):
    """Ask the Writer Agent to create a full blog post from title and outline."""

    def __init__(self, context_tasks: list[Task] | None = None) -> None:
        self._context_tasks = context_tasks or []

    def build(self, agent: Agent) -> Task:
        logger.debug("Building WriterTask")

        return Task(
            description=(
                "Write a blog post for this title: **{selected_title}**\n"
                "Keywords: **{keywords}**\n"
                "Outline: {outline}\n\n"
                "User brief constraints:\n{brief_context}\n\n"
                "Corporate Style Guide:\n{style_guide_instructions}\n\n"
                "Retrieved project knowledge:\n{knowledge_context}\n\n"
                "Task requirements:\n"
                "- Return only the blog content in Markdown, starting with '# {selected_title}'.\n"
                "- Write the full article in Vietnamese.\n"
                "- Follow the corporate style guide strictly.\n"
                "- Do not use forbidden words; use the required replacements.\n"
                "- Do NOT return JSON.\n"
                "- Use clear H2 and H3 sections.\n"
                "- Ground factual and technical claims in the retrieved project knowledge.\n"
                "- If the retrieved knowledge does not support a detail, omit it instead of guessing.\n"
            ),
            expected_output=(
                "A complete Vietnamese blog post in Markdown format, starting with an H1 heading."
            ),
            agent=agent,
            context=self._context_tasks,
        )
