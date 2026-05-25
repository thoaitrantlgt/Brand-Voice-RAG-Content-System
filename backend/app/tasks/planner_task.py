"""
tasks/planner_task.py - Planner Task Definition
SRP: Defines the Planner task only.
"""
from crewai import Agent, Task

from app.core.interfaces import ITask
from app.core.logging import logger


class PlannerTask(ITask):
    """
    Ask the Planner Agent to research the keyword and create one editable draft.
    The draft is returned as JSON so the UI can let the user review it first.
    """

    def build(self, agent: Agent) -> Task:
        logger.debug("Building PlannerTask")

        return Task(
            description=(
                "/nothink\n"
                "Tao 1 ban draft blog cho cac tu khoa chinh: {keywords}\n\n"
                "Truoc khi lap draft, hay tim thong tin lien quan trong tai lieu nguoi dung upload neu co tool Knowledge Base. "
                "Neu co tool Web Search, hay dung web de cap nhat thong tin hien tai. "
                "Khong yeu cau nguoi dung cung cap ngach hoac chuyen muc.\n\n"
                "Draft phai co:\n"
                "- Tieu de bai viet ro rang.\n"
                "- SEO title ngan.\n"
                "- Outline de nguoi dung feedback truoc khi viet, gom cac de muc H2 va cac gach dau dong ben duoi moi de muc.\n\n"
                "Yeu cau: Tra ve dung format JSON, khong giai thich them."
            ),
            expected_output=(
                "JSON object dang sau (tra ve dung JSON, khong them text khac):\n"
                '{"titles": [{"keyword": "tu khoa", "title": "Tieu de bai viet", '
                '"seo_title": "Tieu de SEO ngan", "outline": ['
                '"## De muc 1\\n- Y chinh 1\\n- Y chinh 2", '
                '"## De muc 2\\n- Y chinh 1\\n- Y chinh 2", '
                '"## De muc 3\\n- Y chinh 1\\n- Y chinh 2"]}]}'
            ),
            agent=agent,
            output_json=True,
        )
