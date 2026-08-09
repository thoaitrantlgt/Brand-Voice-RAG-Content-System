import pytest

from app.agents import llm_factory
from app.agents.llm_factory import LLMFactory
from app.core.config import AIProvider, RunMode, Settings


@pytest.mark.parametrize(
    ("model_name", "expected"),
    [
        ("gemini-3.5-flash", "gemini/gemini-3.5-flash"),
        ("gemini/gemini-3.5-flash", "gemini/gemini-3.5-flash"),
    ],
)
def test_google_factory_configures_crewai_llm(monkeypatch, model_name, expected):
    captured = {}

    def fake_llm(**kwargs):
        captured.update(kwargs)
        return kwargs

    monkeypatch.setattr(llm_factory, "LLM", fake_llm)
    settings = Settings(
        RUN_MODE=RunMode.CLOUD,
        AI_PROVIDER=AIProvider.GOOGLE,
        GOOGLE_API_KEY="configured-key",
    )

    result = LLMFactory(settings).create(model_name)

    assert result["model"] == expected
    assert captured["api_key"] == "configured-key"


def test_google_factory_rejects_placeholder_key():
    settings = Settings(
        RUN_MODE=RunMode.CLOUD,
        AI_PROVIDER=AIProvider.GOOGLE,
        GOOGLE_API_KEY="your_google_api_key_here",
    )

    with pytest.raises(ValueError, match="GOOGLE_API_KEY is not configured"):
        LLMFactory(settings).create("gemini-3.5-flash")


def test_vllm_factory_uses_openai_compatible_endpoint(monkeypatch):
    captured = {}

    def fake_llm(**kwargs):
        captured.update(kwargs)
        return kwargs

    monkeypatch.setattr(llm_factory, "LLM", fake_llm)
    settings = Settings(
        RUN_MODE=RunMode.LOCAL,
        AI_PROVIDER=AIProvider.VLLM,
        VLLM_BASE_URL="http://vllm:8000/v1",
        VLLM_API_KEY="internal-token",
    )

    result = LLMFactory(settings).create("qwen3.5-2b")

    assert result["model"] == "openai/qwen3.5-2b"
    assert captured["base_url"] == "http://vllm:8000/v1"
    assert captured["api_key"] == "internal-token"


def test_vllm_factory_requires_base_url():
    settings = Settings(
        RUN_MODE=RunMode.LOCAL,
        AI_PROVIDER=AIProvider.VLLM,
        VLLM_BASE_URL="",
    )

    with pytest.raises(ValueError, match="VLLM_BASE_URL is not configured"):
        LLMFactory(settings).create("qwen3.5-2b")
