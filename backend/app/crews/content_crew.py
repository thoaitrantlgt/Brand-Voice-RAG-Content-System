"""
crews/content_crew.py - Content Generation Crew.
"""
import os
from pathlib import Path
from typing import Any

from crewai import Crew, Process

from app.agents.planner_agent import PlannerAgent
from app.agents.writer_agent import WriterAgent
from app.core.config import Settings
from app.core.exceptions import CrewOrchestrationError
from app.core.interfaces import ICrew, IVectorStore
from app.core.logging import logger
from app.tasks.planner_task import PlannerTask
from app.tasks.writer_task import WriterTask
from app.tools.search_tracker import TrackingSearchTool
from app.tools.web_search_tool import create_web_search_tool


class ContentCrew(ICrew):
    """Orchestrates Planner-only and Writer+Editor content flows."""

    def __init__(
        self,
        settings: Settings,
        vector_store: IVectorStore | None = None,
    ) -> None:
        self._settings = settings
        self._vector_store = vector_store
        storage_dir = Path(settings.CHROMA_PERSIST_DIR).parent / "crewai"
        storage_dir.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("CREWAI_STORAGE_DIR", str(storage_dir.resolve()))

    def _build(
        self,
        inputs: dict,
        tracking_tool: TrackingSearchTool | None = None,
    ) -> Crew:
        logger.info("Building ContentCrew pipeline")

        is_draft_generation = "selected_title" not in inputs
        agents = []
        tasks = []

        if is_draft_generation:
            tools_for_planner = self._build_research_tools(
                inputs=inputs,
                tracking_tool=tracking_tool,
                agent_name="PlannerAgent",
            )
            planner = PlannerAgent(self._settings, tools=tools_for_planner).build()
            planner_task = PlannerTask().build(planner)

            agents.append(planner)
            tasks.append(planner_task)
        else:
            tools_for_writer = self._build_research_tools(
                inputs=inputs,
                tracking_tool=tracking_tool,
                agent_name="WriterAgent",
            )
            writer = WriterAgent(self._settings, tools=tools_for_writer).build()

            from app.agents.editor_agent import EditorAgent
            from app.tasks.editor_task import EditorTask

            editor = EditorAgent(self._settings).build()
            writer_task = WriterTask(context_tasks=[]).build(writer)
            editor_task = EditorTask(context_tasks=[writer_task]).build(editor)

            agents.extend([writer, editor])
            tasks.extend([writer_task, editor_task])

        return Crew(
            agents=agents,
            tasks=tasks,
            process=Process.sequential,
            verbose=self._settings.DEBUG,
            memory=False,
        )

    def _build_research_tools(
        self,
        inputs: dict,
        tracking_tool: TrackingSearchTool | None,
        agent_name: str,
    ) -> list:
        """Build research tools shared by Planner and Writer."""
        tools = []

        if self._vector_store is not None:
            doc_count = self._vector_store.count()
            if doc_count > 0:
                from app.rag.retrieval_engine import RetrievalEngine
                from app.tools.knowledge_base_tool import KnowledgeBaseTool

                retrieval_engine = RetrievalEngine(self._vector_store, self._settings)
                tools.append(KnowledgeBaseTool(
                    retrieval_engine=retrieval_engine,
                    project_id=inputs.get("project_id", "default"),
                    cluster="knowledge",
                ))
                logger.info("KnowledgeBaseTool enabled for {} | {} docs", agent_name, doc_count)
            else:
                logger.info("RAG is empty (0 docs) - {} running without KnowledgeBaseTool", agent_name)
        else:
            logger.info("RAG not configured - {} running without KnowledgeBaseTool", agent_name)

        if inputs.get("use_web_search") and tracking_tool:
            tools.append(tracking_tool)
            logger.info("Serper Web Search enabled for {}", agent_name)

        return tools

    def run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        logger.info("Starting ContentCrew | inputs={}", inputs)

        citations: list[dict[str, Any]] = []
        retrieved_contexts: list[dict[str, Any]] = []
        if self._vector_store is not None and inputs.get("selected_title"):
            from app.rag.retrieval_engine import RetrievalEngine

            query = f"{inputs.get('selected_title', '')} {inputs.get('keywords', '')}".strip()
            chunks = RetrievalEngine(self._vector_store, self._settings).retrieve(
                query=query,
                top_k=2,
                project_id=inputs.get("project_id", "default"),
                cluster="knowledge",
            )
            context = "\n\n".join(str(chunk.get("text", "")) for chunk in chunks)
            citations = [
                {
                    "document_id": str(chunk.get("metadata", {}).get("document_id", "")),
                    "chunk_index": int(str(chunk.get("metadata", {}).get("chunk_index", 0)) or 0),
                    "source_url": chunk.get("metadata", {}).get("source_url"),
                    "excerpt": str(chunk.get("text", ""))[:500],
                    "relevance_score": round(1 - float(chunk.get("distance", 1)), 4),
                }
                for chunk in chunks
                if chunk.get("metadata", {}).get("document_id")
            ]
            retrieved_contexts = [
                {
                    "rank": index,
                    "document_id": str(chunk.get("metadata", {}).get("document_id", "")),
                    "chunk_index": int(str(chunk.get("metadata", {}).get("chunk_index", 0)) or 0),
                    "text": str(chunk.get("text", "")),
                    "relevance_score": round(1 - float(chunk.get("distance", 1)), 4),
                }
                for index, chunk in enumerate(chunks, 1)
            ]
            inputs = {**inputs, "knowledge_context": context[:3000]}
        else:
            inputs = {**inputs, "knowledge_context": "No project knowledge was retrieved."}

        tracking_tool: TrackingSearchTool | None = None
        if inputs.get("use_web_search"):
            try:
                inner = create_web_search_tool(self._settings)
                tracking_tool = TrackingSearchTool(inner_tool=inner)
                logger.info("TrackingSearchTool initialized")
            except Exception as e:
                logger.warning("Web search tool init failed, disabling | error={}", e)
                inputs = {**inputs, "use_web_search": False}

        try:
            crew = self._build(inputs, tracking_tool=tracking_tool)
            result = crew.kickoff(inputs=inputs)
            raw = getattr(result, "raw", None) or str(result) or ""

            logger.info("Raw result type={} | first 300 chars: {}", type(result).__name__, raw[:300])

            if raw and ("Action:" in raw or "Action Input:" in raw) and "{" not in raw and "# " not in raw:
                logger.warning("Tool-call loop detected, attempting tasks_output fallback")
                raw = ""

            if not raw or raw.strip() in ("", "None"):
                logger.warning("Main result empty, attempting tasks_output fallback")
                if hasattr(result, "tasks_output") and result.tasks_output:
                    for task_out in result.tasks_output:
                        candidate = getattr(task_out, "raw", "") or ""
                        if candidate and candidate.strip() not in ("", "None"):
                            raw = candidate
                            logger.info("Fallback to tasks_output: {} chars", len(raw))
                            break

            logger.info("ContentCrew completed | raw_len={}", len(raw))

            result_dict: dict[str, Any] = {
                "raw_output": raw,
                "status": "success",
                "citations": citations,
                "retrieved_contexts": retrieved_contexts,
            }

            if tracking_tool and tracking_tool.collected_links:
                result_dict["search_links"] = tracking_tool.collected_links
                logger.info("Collected {} search links", len(tracking_tool.collected_links))
            if tracking_tool:
                result_dict["seo_research"] = tracking_tool.research_report()

            return result_dict

        except Exception as e:
            logger.error("ContentCrew failed | error={}", e)
            raise CrewOrchestrationError(
                f"Pipeline tao noi dung that bai: {e}",
                {"inputs": inputs},
            ) from e
