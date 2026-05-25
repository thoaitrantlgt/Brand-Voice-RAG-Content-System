"""
agents/qwen3_llm.py — Wrapper cho crewai.LLM để tương thích với Qwen3 Thinking Mode.

Vấn đề: Qwen3 bật thinking mode mặc định → sinh ra <think>...</think> blocks
→ CrewAI nhận empty string vì content thực nằm sau phần thinking bị filter.

Giải pháp: Override method call() để inject /nothink vào user message TRƯỚC khi gửi.
Đây là cách Qwen3 hỗ trợ chính thức để tắt thinking qua token đặc biệt.
"""
from crewai import LLM
from app.core.logging import logger


class Qwen3LLM(LLM):
    """
    Subclass của crewai.LLM với /nothink injection cho Qwen3.
    
    Qwen3 nhận diện /nothink token ở đầu user message và tắt thinking mode,
    cho phép trả về nội dung trực tiếp mà không cần suy nghĩ nội tâm.
    """

    def call(self, messages: list[dict], **kwargs):
        """
        Override call() để inject /nothink vào user message cuối cùng.
        Đây là hook chính CrewAI gọi khi cần LLM response.
        """
        messages = self._inject_nothink(messages)
        return super().call(messages, **kwargs)

    def _inject_nothink(self, messages: list[dict]) -> list[dict]:
        """
        Tìm user message cuối cùng và prepend /nothink nếu chưa có.
        Không thay đổi system messages hay assistant messages.
        """
        if not messages:
            return messages

        result = list(messages)

        # Tìm user message cuối cùng (đi từ dưới lên)
        for i in range(len(result) - 1, -1, -1):
            msg = result[i]
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str) and not content.startswith("/nothink"):
                    result[i] = {**msg, "content": f"/nothink\n{content}"}
                    logger.debug("Injected /nothink into user message (idx={})", i)
                break

        return result
