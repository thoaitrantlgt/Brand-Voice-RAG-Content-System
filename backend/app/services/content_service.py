"""
services/content_service.py — Content Generation Business Logic
SRP: Layer trung gian giữa API router và Crew orchestration.
DIP: Depend vào ICrew abstraction, không phải ContentCrew cụ thể.
"""
from typing import Any

from app.core.interfaces import ICrew
from app.core.exceptions import ContentGenerationError
from app.core.logging import logger
from app.agents.llm_factory import LLMFactory


class ContentService:
    """
    Service layer xử lý business logic cho việc tạo nội dung blog.
    Tách biệt API routing khỏi Crew orchestration — dễ test và mở rộng.

    DIP: Nhận ICrew qua constructor injection, không tự khởi tạo.
    """

    def __init__(self, crew: ICrew) -> None:
        """
        Args:
            crew: Implementation của ICrew (thường là ContentCrew).
                  Inject từ dependency container — dễ mock trong tests.
        """
        self._crew = crew

    async def generate_titles(
        self,
        keywords: list[str],
        use_web_search: bool = False,
    ) -> dict[str, Any]:
        """
        Chạy Planner Agent để tạo danh sách plan nháp bài viết.
        """
        logger.info("Generating title plans | keywords={} web_search={}", keywords, use_web_search)

        try:
            result = self._crew.run(inputs={
                "keywords": ", ".join(keywords),
                "use_web_search": use_web_search,
            })
            
            # Xử lý parse JSON từ kết quả trả về của LLM (đặc biệt với models nhả thêm text)
            import json
            import re
            raw_output = result.get("raw_output", "")
            
            clean_json = ""
            # Thử tìm block ```json ... ```
            match = re.search(r'```json\s*(.*?)\s*```', raw_output, re.DOTALL)
            if match:
                clean_json = match.group(1)
            else:
                # Fallback: Tìm từ dấu { đầu tiên tới dấu } cuối cùng
                start = raw_output.find('{')
                end = raw_output.rfind('}')
                if start != -1 and end != -1:
                    clean_json = raw_output[start:end+1]
                else:
                    clean_json = raw_output.strip()
            
            # Sửa lỗi phổ biến của model nhỏ: in ra dấu [...] thay vì mảng thực tế
            clean_json = clean_json.replace("[...]", '["..."]')
            clean_json = clean_json.replace(", ...", "")
            
            # Nếu chuỗi bị cắt ngang ở cuối, cố gắng đóng ngoặc
            if clean_json.count("[") > clean_json.count("]"):
                clean_json += "]"
            if clean_json.count("{") > clean_json.count("}"):
                clean_json += "}"
            
            try:
                parsed_data = json.loads(clean_json)
                if not parsed_data.get("titles"):
                    raise json.JSONDecodeError("Missing titles", "", 0)
            except (json.JSONDecodeError, ValueError):
                # Nếu LLM quá nhỏ và nói lảm nhảm, không sinh ra JSON, ta trả về dữ liệu mẫu (Fallback)
                # Để người dùng có thể tiếp tục luồng và hiểu ứng dụng hoạt động ra sao.
                logger.error("LLM không trả về JSON hợp lệ: {}", raw_output)
                parsed_data = {
                    "titles": [
                        {
                            "keyword": keywords[0] if keywords else "AI",
                            "title": f"Hướng dẫn chi tiết về {keywords[0] if keywords else 'AI'}",
                            "seo_title": f"Hướng dẫn chi tiết về {keywords[0] if keywords else 'AI'} năm 2024",
                            "outline": ["Mở đầu", "Khái niệm", "Ứng dụng", "Kết luận"]
                        }
                    ]
                }

            parsed_data["titles"] = self._normalize_draft_plans(
                parsed_data.get("titles", []),
                fallback_keyword=keywords[0] if keywords else "AI",
            )

            merged = {**result, **parsed_data}
            # Pass through search_links from crew if available
            if result.get("search_links"):
                merged["search_links"] = result["search_links"]
            return merged

        except Exception as e:
            raise ContentGenerationError(
                f"Không thể tạo plan nháp: {e}",
                {"keywords": keywords},
            ) from e

    def _normalize_draft_plans(
        self,
        titles: list[dict[str, Any]],
        fallback_keyword: str,
    ) -> list[dict[str, Any]]:
        """Keep one editable draft and make outline lines useful for feedback."""
        if not titles:
            titles = [{}]

        plan = titles[0]
        outline = plan.get("outline") or []
        if isinstance(outline, str):
            outline = [line.strip() for line in outline.splitlines() if line.strip()]

        normalized_outline: list[str] = []
        for item in outline:
            text = str(item).strip()
            if not text:
                continue
            if text.startswith("#") or "\n-" in text or "\n* " in text:
                normalized_outline.append(text)
            else:
                normalized_outline.append(f"## {text}\n- Ý chính cần triển khai\n- Dữ kiện hoặc ví dụ cần bổ sung")

        if not normalized_outline:
            normalized_outline = [
                "## Mở đầu\n- Bối cảnh chính của chủ đề\n- Lý do người đọc nên quan tâm",
                "## Nội dung chính\n- Các luận điểm quan trọng\n- Dữ kiện hoặc ví dụ hỗ trợ",
                "## Kết luận\n- Tóm tắt ý chính\n- Gợi ý hành động tiếp theo",
            ]

        title = plan.get("title") or f"Hướng dẫn chi tiết về {fallback_keyword}"
        return [
            {
                "keyword": plan.get("keyword") or fallback_keyword,
                "title": title,
                "seo_title": plan.get("seo_title") or title,
                "outline": normalized_outline,
            }
        ]

    async def generate_content(
        self,
        keywords: list[str],
        selected_title: str,
        outline: list[str] | None = None,
        use_web_search: bool = False,
    ) -> dict[str, Any]:
        """
        Chạy Writer + Editor Agent để tạo bài viết hoàn chỉnh.

        Args:
            keywords: Từ khóa chính để tối ưu SEO.
            selected_title: Tiêu đề đã được người dùng chọn.
            outline: Outline tùy chỉnh (optional).

        Returns:
            Dict chứa bài viết đã tối ưu SEO.
        """
        logger.info("Generating content | title={}", selected_title)

        try:
            result = self._crew.run(inputs={
                "keywords": ", ".join(keywords),
                "selected_title": selected_title,
                "outline": "\n".join(outline) if outline else "",
                "use_web_search": use_web_search,
            })
            
            import json
            import re
            raw_output = result.get("raw_output", "")
            
            logger.info("Raw output length: {} chars | preview: {}", len(raw_output), raw_output[:200])
            
            # Bỏ qua cố gắng parse JSON vì WriterTask giờ chỉ trả về Markdown trực tiếp.
            # Tìm dòng đầu tiên có '# ' để làm title
            lines = raw_output.split('\n')
            title_tag = selected_title
            
            # Cố gắng tìm thẻ H1
            h1_match = re.search(r'^# (.+)', raw_output, re.MULTILINE)
            if h1_match:
                title_tag = h1_match.group(1).strip()
            
            parsed_data = {
                "title_tag": title_tag,
                "meta_description": f"Bài viết chuyên sâu về {', '.join(keywords[:2])}",
                "optimized_content": raw_output.strip()
            }
            
            logger.info(
                "Final parsed | content={} chars",
                len(parsed_data.get("optimized_content", "")),
            )
            
            return {**result, **parsed_data}

        except Exception as e:
            raise ContentGenerationError(
                f"Không thể tạo nội dung bài viết: {e}",
                {"title": selected_title},
            ) from e

    async def rewrite_content(self, original_text: str, feedback: str) -> dict[str, Any]:
        """
        Sửa lại một đoạn văn bản dựa trên feedback của người dùng (Inline Comment).
        Đây là một LLM call độc lập, không thông qua CrewAI pipeline.
        """
        logger.info("Rewriting content | feedback={}", feedback)
        
        try:
            # Khởi tạo LLM từ factory bằng settings của crew
            llm_factory = LLMFactory(self._crew._settings)
            llm = llm_factory.create(self._crew._settings.EDITOR_MODEL)
            
            prompt = (
                f"Bạn là một biên tập viên xuất sắc. Hãy sửa lại đoạn văn bản sau "
                f"dựa trên yêu cầu của người dùng.\n\n"
                f"Đoạn văn bản gốc:\n{original_text}\n\n"
                f"Yêu cầu sửa đổi:\n{feedback}\n\n"
                f"Vui lòng CHỈ trả về đoạn văn bản đã được sửa, không giải thích, không kèm markdown code block (trừ khi là format cần thiết)."
            )
            
            # Gọi LLM (crewai.LLM / litellm)
            response = llm.call([{"role": "user", "content": prompt}])
            
            return {
                "rewritten_text": response.strip(),
                "status": "success",
            }
        except Exception as e:
            raise ContentGenerationError(
                f"Không thể re-write nội dung: {e}",
                {"feedback": feedback},
            ) from e
