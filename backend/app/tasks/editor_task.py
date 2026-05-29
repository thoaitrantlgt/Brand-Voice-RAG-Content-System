"""
tasks/editor_task.py - Editor Task Definition.
"""
from crewai import Agent, Task

from app.core.interfaces import ITask
from app.core.logging import logger


class EditorTask(ITask):
    """Ask the Editor Agent to refine the Writer output before deterministic checks."""

    def __init__(self, context_tasks: list[Task] | None = None) -> None:
        self._context_tasks = context_tasks or []

    def build(self, agent: Agent) -> Task:
        logger.debug("Building EditorTask")

        return Task(
            description=(
                "Review the blog post drafted by the Writer Agent.\n\n"
                "Keywords: **{keywords}**\n\n"
                "Corporate Style Guide:\n{style_guide_instructions}\n\n"
                "Your tasks:\n"
                "1. Refine the content for clarity, engagement, and accuracy.\n"
                "2. Ensure the tone is consistent, professional, formal, and direct.\n"
                "3. Apply the corporate terminology rules and avoid forbidden terms.\n"
                "4. Optimize headings (H1, H2, H3) and structure for readability.\n"
                "5. Fix grammatical or spelling errors.\n"
                "6. Maintain the original Markdown format.\n\n"
                "OUTPUT FORMAT:\n"
                "Return the complete, refined blog post in Markdown format. Start with the # H1 heading. "
                "Do NOT return JSON."
            ),
            expected_output=(
                "The fully refined and edited blog post in Markdown format."
            ),
            agent=agent,
            context=self._context_tasks,
        )
