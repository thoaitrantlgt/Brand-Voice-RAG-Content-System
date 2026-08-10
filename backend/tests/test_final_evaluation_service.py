import sys
from types import SimpleNamespace

from app.core.config import AIProvider, Settings
from app.services.final_evaluation_service import FinalEvaluationService


class FakeLLM:
    def __init__(self, response: str):
        self.response = response
        self.messages = None

    def call(self, messages):
        self.messages = messages
        return self.response


def test_vllm_final_judge_uses_configured_endpoint_without_nothink(monkeypatch):
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured["request"] = kwargs
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"summary":"ok"}'))]
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    settings = Settings(
        FINAL_JUDGE_PROVIDER=AIProvider.VLLM,
        FINAL_JUDGE_MODEL="qwen3.5-2b",
        VLLM_BASE_URL="http://vllm:8000/v1",
        VLLM_API_KEY="internal-token",
    )

    result = FinalEvaluationService(settings)._create_llm().call(
        [{"role": "user", "content": "Evaluate this article"}]
    )

    assert result == '{"summary":"ok"}'
    assert captured["client"] == {
        "api_key": "internal-token",
        "base_url": "http://vllm:8000/v1",
    }
    assert captured["request"]["model"] == "qwen3.5-2b"
    assert captured["request"]["messages"][0]["content"] == "Evaluate this article"


def test_final_evaluation_preserves_scores_and_maps_exact_quote():
    content = "# Giữ hơi khi hát\n\nBạn không nên ép cổ khi luyện tập.\n\n## Bài tập\n\nTập đều mỗi ngày."
    llm = FakeLLM(
        """```json
        {
          "summary": "Bài đúng cấu trúc nhưng còn một hướng dẫn cần rõ hơn.",
          "dimensions": [
            {"metric": "brand", "score": 1, "reason": "Giọng hướng dẫn phù hợp.", "deductions": [
              {"criterion": "Tone", "points": 3, "reason": "Một số câu còn trung tính.", "suggestion": "Dùng giọng hướng dẫn rõ hơn."},
              {"criterion": "Từ vựng", "points": 1, "reason": "Thiếu từ khóa thương hiệu.", "suggestion": "Bổ sung thuật ngữ ưu tiên."}
            ]},
            {"metric": "style", "score": 2, "reason": "Cấu trúc rõ."},
            {"metric": "fingerprint", "score": 3, "reason": "Nhịp câu chưa thật đặc trưng."},
            {"metric": "persona", "score": 4, "reason": "Phù hợp người mới."}
          ],
          "annotations": [
            {
              "quote": "Tập đều mỗi ngày.",
              "metric": "fingerprint",
              "severity": "warning",
              "reason": "Hướng dẫn còn chung chung.",
              "suggestion": "Nêu thời lượng cụ thể."
            },
            {
              "quote": "Đoạn không tồn tại",
              "metric": "style",
              "severity": "error",
              "reason": "Model bịa quote.",
              "suggestion": ""
            }
          ]
        }
        ```"""
    )
    settings = Settings(
        FINAL_JUDGE_ENABLED=True,
        FINAL_JUDGE_PROVIDER=AIProvider.OPENAI,
        FINAL_JUDGE_MODEL="qwen3.5-2b",
    )
    service = FinalEvaluationService(settings, llm=llm)

    result = service.evaluate(
        content=content,
        brief={"topic": "Giữ hơi", "audience": "Người mới"},
        quality_report={
            "passed": True,
            "dimension_scores": {"brand": 84, "style": 92, "fingerprint": 55, "persona": 73},
            "violations": [],
        },
        profile=None,
    )

    assert result["status"] == "evaluated"
    assert result["overall_score"] == 76
    assert [item["score"] for item in result["dimensions"]] == [84, 92, 55, 73]
    assert [item["points"] for item in result["dimensions"][0]["deductions"]] == [12, 4]
    assert sum(item["points"] for item in result["dimensions"][0]["deductions"]) == 16
    assert sum(item["points"] for item in result["dimensions"][2]["deductions"]) == 45
    assert result["annotations"][0]["quote"] == "Tập đều mỗi ngày."
    assert result["annotations"][0]["line"] == 7
    assert result["annotations"][0]["column"] == 1
    assert result["annotations"][0]["start"] == content.index("Tập đều")
    assert result["unmapped_annotation_count"] == 1
    assert "Các điểm số" in llm.messages[0]["content"]


def test_final_evaluation_returns_safe_error_payload():
    class BrokenLLM:
        def call(self, messages):
            raise RuntimeError("judge unavailable")

    service = FinalEvaluationService(Settings(), llm=BrokenLLM())
    result = service.evaluate(
        content="# Test\n\nBody",
        brief={"topic": "Test"},
        quality_report={
            "passed": False,
            "dimension_scores": {"brand": 50},
        },
    )

    assert result["status"] == "error"
    assert result["passed"] is False
    assert result["annotations"] == []
    assert result["dimensions"][0]["score"] == 50
    assert result["dimensions"][0]["deductions"][0]["points"] == 50


def test_final_evaluation_fallback_uses_real_component_scores_for_deductions():
    service = FinalEvaluationService(Settings(FINAL_JUDGE_ENABLED=False))
    result = service.evaluate(
        content="# Test\n\nBody",
        brief={"topic": "Test"},
        quality_report={
            "passed": True,
            "dimension_scores": {"brand": 90},
            "score_breakdown": {
                "brand": [
                    {"criterion": "Tone thương hiệu", "score": 100},
                    {"criterion": "Từ vựng thương hiệu", "score": 80},
                    {"criterion": "Nhận diện thương hiệu", "score": 90},
                ]
            },
        },
    )

    deductions = result["dimensions"][0]["deductions"]
    assert [item["criterion"] for item in deductions] == [
        "Từ vựng thương hiệu",
        "Nhận diện thương hiệu",
    ]
    assert sum(item["points"] for item in deductions) == 10


def test_component_scores_split_a_collapsed_model_deduction():
    service = FinalEvaluationService(Settings())
    deductions = service._normalize_deductions(
        [
            {
                "criterion": "Nhận diện thương hiệu",
                "points": 11,
                "reason": "Định vị thương hiệu chưa đủ rõ.",
                "suggestion": "Bổ sung thông điệp định vị.",
            }
        ],
        metric="brand",
        score=89,
        reason="Brand đạt 89/100.",
        quality_report={
            "score_breakdown": {
                "brand": [
                    {"criterion": "Tone thương hiệu", "score": 100},
                    {"criterion": "Từ vựng thương hiệu", "score": 90},
                    {"criterion": "Nhận diện thương hiệu", "score": 76},
                ]
            }
        },
    )

    assert [(item["criterion"], item["points"]) for item in deductions] == [
        ("Từ vựng thương hiệu", 3),
        ("Nhận diện thương hiệu", 8),
    ]
    assert deductions[1]["reason"] == "Định vị thương hiệu chưa đủ rõ."


def test_final_evaluation_accepts_improvement_for_passing_metric():
    content = "# Bài viết\n\nĐoạn này rõ ràng nhưng vẫn có thể ngắn gọn hơn."
    llm = FakeLLM(
        """{
          "summary": "Bài đạt nhưng còn một câu có thể gọn hơn.",
          "dimensions": [{"metric": "style", "reason": "Style tổng thể đạt."}],
          "annotations": [{
            "quote": "Đoạn này rõ ràng nhưng vẫn có thể ngắn gọn hơn.",
            "metric": "style",
            "severity": "warning",
            "reason": "Câu hơi dài.",
            "suggestion": "Rút gọn câu."
          }]
        }"""
    )
    service = FinalEvaluationService(Settings(), llm=llm)

    result = service.evaluate(
        content=content,
        brief={"topic": "Bài viết"},
        quality_report={"passed": True, "dimension_scores": {"style": 92}},
    )

    assert [item["metric"] for item in result["dimensions"]] == ["style"]
    assert result["overall_score"] == 92
    assert result["passed"] is True
    assert result["annotations"][0]["metric"] == "style"
    assert result["annotations"][0]["severity"] == "warning"
