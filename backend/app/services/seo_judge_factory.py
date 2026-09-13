"""Create an independently configured LLM for subjective SEO dimensions."""
from __future__ import annotations

from typing import Any

from app.agents.llm_factory import LLMFactory
from app.core.config import AIProvider, RunMode, Settings


def create_seo_judge(settings: Settings) -> Any:
    provider = settings.SEO_LLM_JUDGE_PROVIDER
    if provider in {AIProvider.OPENAI, AIProvider.VLLM}:
        from openai import OpenAI

        if provider == AIProvider.OPENAI:
            base_url = settings.SEO_LLM_JUDGE_API_BASE or settings.OPENAI_API_BASE
            api_key = (
                settings.SEO_LLM_JUDGE_API_KEY
                or settings.OPENAI_API_KEY
                or "local-seo-judge"
            )
        else:
            base_url = settings.SEO_LLM_JUDGE_API_BASE or settings.VLLM_BASE_URL
            api_key = (
                settings.SEO_LLM_JUDGE_API_KEY
                or settings.VLLM_API_KEY
                or "local-seo-judge"
            )
        if not base_url:
            raise ValueError("SEO_LLM_JUDGE_API_BASE is required for an OpenAI-compatible judge")

        client = OpenAI(api_key=api_key, base_url=base_url)
        model = settings.SEO_LLM_JUDGE_MODEL
        inject_nothink = "127.0.0.1" in base_url or "localhost" in base_url

        class OpenAICompatibleSeoJudge:
            def call(self, messages: list[dict[str, Any]]) -> str:
                prepared = [dict(message) for message in messages]
                if inject_nothink:
                    for index in range(len(prepared) - 1, -1, -1):
                        if prepared[index].get("role") == "user":
                            content = str(prepared[index].get("content") or "")
                            if not content.startswith("/nothink"):
                                prepared[index]["content"] = f"/nothink\n{content}"
                            break
                response = client.chat.completions.create(
                    model=model,
                    messages=prepared,
                    temperature=0.1,
                    max_tokens=2048,
                )
                return response.choices[0].message.content or ""

        return OpenAICompatibleSeoJudge()

    updates: dict[str, Any] = {
        "AI_PROVIDER": provider,
        "RUN_MODE": (
            RunMode.LOCAL
            if provider in {AIProvider.OPENAI, AIProvider.VLLM, AIProvider.OLLAMA}
            else RunMode.CLOUD
        ),
    }
    if provider == AIProvider.GOOGLE:
        updates["GOOGLE_API_KEY"] = (
            settings.SEO_LLM_JUDGE_API_KEY or settings.GOOGLE_API_KEY
        )
    elif provider == AIProvider.ANTHROPIC:
        updates["ANTHROPIC_API_KEY"] = (
            settings.SEO_LLM_JUDGE_API_KEY or settings.ANTHROPIC_API_KEY
        )
    elif provider == AIProvider.HUGGINGFACE:
        updates["HUGGINGFACE_API_KEY"] = (
            settings.SEO_LLM_JUDGE_API_KEY or settings.HUGGINGFACE_API_KEY
        )
    elif provider == AIProvider.OLLAMA and settings.SEO_LLM_JUDGE_API_BASE:
        updates["OLLAMA_BASE_URL"] = settings.SEO_LLM_JUDGE_API_BASE
    judge_settings = settings.model_copy(update=updates)
    return LLMFactory(judge_settings).create(settings.SEO_LLM_JUDGE_MODEL)
