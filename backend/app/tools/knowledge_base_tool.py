"""
tools/knowledge_base_tool.py — Knowledge Base Search Tool (Phase 2)
SRP: Tool này chỉ chịu trách nhiệm truy xuất tài liệu từ ChromaDB.
DIP: Depend vào RetrievalEngine abstraction, không gọi ChromaDB trực tiếp.

Writer Agent dùng tool này để tìm kiếm tài liệu người dùng đã upload
và inject kết quả vào nội dung bài viết.
"""
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from app.core.exceptions import ToolExecutionError
from app.core.logging import logger
from app.rag.retrieval_engine import RetrievalEngine


class KnowledgeBaseInput(BaseModel):
    """Input schema cho Knowledge Base Search Tool."""
    query: str = Field(
        description=(
            "Câu query tìm kiếm bằng ngôn ngữ tự nhiên. "
            "Ví dụ: 'best practices for REST API design' hoặc 'lợi ích của microservices'."
        )
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Số tài liệu tham khảo tối đa cần lấy.",
    )
    document_id: str | None = Field(
        default=None,
        description="Nếu muốn giới hạn tìm kiếm trong một tài liệu cụ thể, cung cấp document_id.",
    )


class KnowledgeBaseTool(BaseTool):
    """
    Custom CrewAI Tool cho phép Writer Agent tìm kiếm tài liệu
    người dùng đã upload vào Knowledge Hub (ChromaDB).

    DIP: Nhận RetrievalEngine qua constructor — không tự khởi tạo.
    """
    name: str = "knowledge_base_search"
    description: str = (
        "Tìm kiếm trong Knowledge Hub (tài liệu người dùng đã upload) "
        "để lấy thông tin tham khảo liên quan đến chủ đề đang viết. "
        "Dùng tool này khi cần dẫn chứng, số liệu, hoặc thông tin chuyên sâu "
        "từ tài liệu nội bộ. Trả về các đoạn văn bản liên quan nhất."
    )
    args_schema: type[BaseModel] = KnowledgeBaseInput

    # Pydantic field để inject RetrievalEngine
    retrieval_engine: RetrievalEngine

    model_config = {"arbitrary_types_allowed": True}

    def _run(
        self,
        query: str,
        top_k: int = 5,
        document_id: str | None = None,
    ) -> str:
        """
        Thực hiện semantic search trong Knowledge Hub.

        Returns:
            Formatted string chứa các đoạn văn bản liên quan nhất,
            sẵn sàng để agent đọc và tích hợp vào bài viết.

        Raises:
            ToolExecutionError: Nếu retrieval thất bại.
        """
        logger.debug(
            "KnowledgeBaseTool._run | query='{}' top_k={}",
            query[:60],
            top_k,
        )

        try:
            context = self.retrieval_engine.retrieve_as_context(
                query=query,
                top_k=top_k,
                document_id=document_id,
            )
            return context

        except Exception as e:
            raise ToolExecutionError(
                f"Knowledge Base search thất bại: {e}",
                {"query": query},
            ) from e
