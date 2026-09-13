from app.agents.llm_factory import LLMFactory
from app.core.config import AIProvider, Settings
from app.core.config import RunMode
from app.services.seo_judge_factory import create_seo_judge


def test_seo_judge_can_use_lm_studio_without_changing_generation_provider(monkeypatch):
    captured: dict = {}

    class Completions:
        def create(self, **kwargs):
            captured["request"] = kwargs
            message = type("Message", (), {"content": '{"ok": true}'})()
            choice = type("Choice", (), {"message": message})()
            return type("Response", (), {"choices": [choice]})()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.chat = type("Chat", (), {"completions": Completions()})()

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    settings = Settings(
        AI_PROVIDER=AIProvider.GOOGLE,
        SEO_LLM_JUDGE_PROVIDER=AIProvider.OPENAI,
        SEO_LLM_JUDGE_MODEL="qwen3.5-2b",
        SEO_LLM_JUDGE_API_BASE="http://127.0.0.1:1234/v1",
        SEO_LLM_JUDGE_API_KEY="lm-studio",
    )

    judge = create_seo_judge(settings)
    assert judge.call([{"role": "user", "content": "Judge this"}]) == '{"ok": true}'
    assert settings.AI_PROVIDER == AIProvider.GOOGLE
    assert captured["client"]["base_url"] == "http://127.0.0.1:1234/v1"
    assert captured["request"]["model"] == "qwen3.5-2b"
    assert captured["request"]["messages"][-1]["content"].startswith("/nothink\n")


def test_seo_judge_can_use_an_independent_google_api_key(monkeypatch):
    captured = {}

    def fake_create(self, model_name=None):
        captured["settings"] = self._settings
        captured["model"] = model_name
        return "google-seo-judge"

    monkeypatch.setattr(LLMFactory, "create", fake_create)
    settings = Settings(
        AI_PROVIDER=AIProvider.OPENAI,
        GOOGLE_API_KEY="generation-key",
        SEO_LLM_JUDGE_PROVIDER=AIProvider.GOOGLE,
        SEO_LLM_JUDGE_MODEL="gemini-2.5-flash",
        SEO_LLM_JUDGE_API_KEY="seo-only-key",
    )

    assert create_seo_judge(settings) == "google-seo-judge"
    assert settings.AI_PROVIDER == AIProvider.OPENAI
    assert captured["settings"].AI_PROVIDER == AIProvider.GOOGLE
    assert captured["settings"].RUN_MODE == RunMode.CLOUD
    assert captured["settings"].GOOGLE_API_KEY == "seo-only-key"
    assert captured["model"] == "gemini-2.5-flash"
