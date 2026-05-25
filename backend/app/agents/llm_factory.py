"""
agents/llm_factory.py — LLM Factory
OCP + DIP: Tạo LLM object mà không để Agent biết provider cụ thể là gì.
Thêm provider mới: chỉ thêm case mới trong factory — không sửa Agent.
"""
from typing import Any
from crewai import LLM

from app.core.config import AIProvider, RunMode, Settings
from app.core.exceptions import UnsupportedProviderError
from app.core.logging import logger

# Import lazy để tránh circular import (Qwen3LLM import LLM từ crewai)
try:
    from app.agents.qwen3_llm import Qwen3LLM
except ImportError:
    Qwen3LLM = LLM  # Fallback an toàn nếu file chưa tồn tại


class LLMFactory:
    """
    Factory class tạo crewai.LLM theo cấu hình Settings.
    Agent nhận LLM từ factory — không tự khởi tạo LLM (DIP).

    Phase 2: Bổ sung HuggingFace Inference API và Local pipeline mode.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(self, model_name: str | None = None) -> Any:
        """
        Tạo LLM object phù hợp với RUN_MODE và AI_PROVIDER hiện tại.

        Args:
            model_name: Override tên model cụ thể (dùng cho từng agent riêng).

        Returns:
            crewai.LLM đã cấu hình.

        Raises:
            UnsupportedProviderError: Nếu provider chưa được hỗ trợ.
        """
        s = self._settings

        if s.RUN_MODE == RunMode.LOCAL:
            # LOCAL mode: Ollama → default | HUGGINGFACE → dùng HF local pipeline
            if s.AI_PROVIDER == AIProvider.HUGGINGFACE:
                return self._create_huggingface_local(
                    model_name or s.HUGGINGFACE_MODEL_ID
                )
            return self._create_local(model_name or s.LOCAL_MODEL_NAME)

        # Cloud mode — dispatch theo provider
        provider = s.AI_PROVIDER
        if provider == AIProvider.GOOGLE:
            return self._create_google(model_name or s.PLANNER_MODEL)
        elif provider == AIProvider.OPENAI:
            return self._create_openai(model_name or s.PLANNER_MODEL)
        elif provider == AIProvider.ANTHROPIC:
            return self._create_anthropic(model_name or s.PLANNER_MODEL)
        elif provider == AIProvider.HUGGINGFACE:
            # Cloud HuggingFace Inference API
            return self._create_huggingface_api(
                model_name or s.HUGGINGFACE_MODEL_ID
            )
        else:
            raise UnsupportedProviderError(
                f"Provider '{provider}' chưa được hỗ trợ.",
                {"supported": [p.value for p in AIProvider]},
            )

    def _create_google(self, model: str) -> LLM:
        logger.debug("Creating Google LLM | model={}", model)
        return LLM(
            model=f"gemini/{model}",
            api_key=self._settings.GOOGLE_API_KEY,
        )

    def _create_openai(self, model: str) -> LLM:
        logger.debug("Creating OpenAI LLM | model={}", model)
        
        formatted_model = model if model.startswith("openai/") else f"openai/{model}"
        base_url = self._settings.OPENAI_API_BASE
        is_local = base_url and ("127.0.0.1" in base_url or "localhost" in base_url)
        
        llm_kwargs: dict = {
            "model": formatted_model,
            "api_key": self._settings.OPENAI_API_KEY,
            "base_url": base_url,
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        
        if is_local:
            # /nothink injection via Qwen3LLM wrapper is the ONLY working approach.
            # enable_thinking=False in extra_body causes EMPTY response (confirmed by test).
            logger.info("Local server detected — using Qwen3LLM wrapper (/nothink injection)")
            return Qwen3LLM(**llm_kwargs)
        
        return LLM(**llm_kwargs)

    def _create_anthropic(self, model: str) -> LLM:
        logger.debug("Creating Anthropic LLM | model={}", model)
        return LLM(
            model=f"anthropic/{model}",
            api_key=self._settings.ANTHROPIC_API_KEY,
        )

    def _create_local(self, model: str) -> LLM:
        logger.debug("Creating Local LLM (Ollama) | model={}", model)
        return LLM(
            model=f"ollama/{model}",
            base_url=self._settings.OLLAMA_BASE_URL,
        )

    def _create_huggingface_api(self, model: str) -> LLM:
        """
        HuggingFace Inference API (cloud) — cần HUGGINGFACE_API_KEY.
        Phù hợp với mô hình lớn trên HF Hub mà không cần phần cứng mạnh.
        """
        logger.debug("Creating HuggingFace Inference API LLM | model={}", model)
        return LLM(
            model=f"huggingface/{model}",
            api_key=self._settings.HUGGINGFACE_API_KEY,
        )

    def _create_huggingface_local(self, model_id: str) -> Any:
        """
        HuggingFace local pipeline — chạy trực tiếp trên máy, không cần API key.
        Sử dụng transformers + LangChain HuggingFacePipeline thay vì LiteLLM.
        Lưu ý: model_id phải là tên repository trên HF (vd: Qwen/Qwen2.5-0.5B) 
        hoặc đường dẫn thư mục model đã tải về (không dùng cho file .gguf).
        """
        logger.info("Đang nạp HuggingFace Local pipeline trực tiếp vào RAM | model={}", model_id)
        
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
            from langchain_huggingface import HuggingFacePipeline
        except ImportError as e:
            logger.error("Thiếu thư viện transformers hoặc langchain_huggingface: {}", e)
            raise RuntimeError("Vui lòng chạy lệnh: pip install transformers torch langchain-huggingface") from e

        # Nạp tokenizer
        tokenizer = AutoTokenizer.from_pretrained(model_id)
        
        # Nạp model. Nếu có GPU sẽ tự động đẩy vào GPU (device_map="auto")
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            device_map="auto",
            trust_remote_code=True,
        )

        # Tạo Text Generation Pipeline
        pipe = pipeline(
            "text-generation",
            model=model,
            tokenizer=tokenizer,
            max_new_tokens=1024,
            temperature=0.7,
            do_sample=True,
            return_full_text=False
        )

        # Bọc lại bằng LangChain HuggingFacePipeline (được CrewAI hỗ trợ)
        return HuggingFacePipeline(pipeline=pipe)
