from types import SimpleNamespace

import pytest

from app.evaluation.deepeval_brand import DeepEvalBrandEvaluator
from app.evaluation.models import BlogEvaluationCase
from app.evaluation.ragas_grounding import RagasGroundingEvaluator, RagasMetricBinding
from scripts.run_advanced_evaluation import render_report, summarize_metrics


def _case(reference: str | None = "Reference article") -> BlogEvaluationCase:
    return BlogEvaluationCase(
        case_id="tss-2",
        brief={
            "topic": "Cách lấy hơi đúng",
            "audience": "Người mới học hát",
            "objective": "Hướng dẫn thực hành",
            "must_cover": ["tư thế", "bài tập"],
            "must_avoid": ["cam kết tuyệt đối"],
        },
        actual_output="# Cách lấy hơi đúng\n\nBài viết hướng dẫn gần gũi.",
        retrieval_contexts=["Giữ vai thả lỏng khi lấy hơi."],
        reference_output=reference,
        brand_profile={"tone": {"primary": "gần gũi và khích lệ"}},
    )


def test_evaluation_case_exposes_complete_brief_and_rag_payload():
    case = _case()

    assert "Người mới học hát" in case.input_text()
    assert "cam kết tuyệt đối" in case.input_text()
    assert case.ragas_payload() == {
        "user_input": case.input_text(),
        "response": case.actual_output,
        "retrieved_contexts": ["Giữ vai thả lỏng khi lấy hơi."],
        "reference": "Reference article",
    }


def test_evaluation_case_compacts_non_scoring_profile_sections():
    case = _case()
    profile = {
        **case.brand_profile,
        "calibration_tests": ["large payload"],
        "prompt_templates": {"blog": "large prompt"},
        "vocabulary": {"repeated_terms": [str(index) for index in range(30)]},
    }
    compacted = BlogEvaluationCase(
        case_id=case.case_id,
        brief=case.brief,
        actual_output=case.actual_output,
        brand_profile=profile,
    ).evaluation_profile()

    assert "calibration_tests" not in compacted
    assert "prompt_templates" not in compacted
    assert len(compacted["vocabulary"]["repeated_terms"]) == 12


def test_ragas_payload_bounds_reference_for_small_local_judge_context():
    case = _case(reference="a" * 5000)

    assert len(case.ragas_payload()["reference"]) == 4000


class FakeDeepEvalMetric:
    def __init__(self, name: str, score: float, threshold: float = 0.8):
        self.name = name
        self.next_score = score
        self.threshold = threshold
        self.reason = f"Reason for {name}"
        self.score = 0.0
        self.success = False

    def measure(self, test_case, **_kwargs):
        assert test_case.input
        assert test_case.actual_output.startswith("# ")
        self.score = self.next_score
        self.success = self.score >= self.threshold
        return self.score


def test_deepeval_brand_report_has_dimension_scores_reasons_and_gate():
    metrics = [
        FakeDeepEvalMetric("tone", 0.9),
        FakeDeepEvalMetric("brief_adherence", 0.75),
    ]
    evaluator = DeepEvalBrandEvaluator(
        metrics=metrics,
        test_case_factory=lambda case: SimpleNamespace(
            input=case.input_text(), actual_output=case.actual_output
        ),
    )

    report = evaluator.evaluate(_case())

    assert report["framework"] == "deepeval"
    assert report["overall_score"] == 0.825
    assert report["passed"] is False
    assert report["metrics"]["tone"]["reason"] == "Reason for tone"


class FakeRagasMetric:
    def __init__(self, score: float):
        self.score = score
        self.samples = []

    async def single_turn_ascore(self, sample):
        self.samples.append(sample)
        return self.score


@pytest.mark.asyncio
async def test_ragas_skips_reference_metrics_without_reference():
    faithfulness = FakeRagasMetric(0.9)
    recall = FakeRagasMetric(0.1)
    evaluator = RagasGroundingEvaluator(
        metrics=[
            RagasMetricBinding("faithfulness", faithfulness, threshold=0.8),
            RagasMetricBinding(
                "context_recall", recall, threshold=0.7, requires_reference=True
            ),
        ],
        sample_factory=lambda payload: payload,
    )

    report = await evaluator.evaluate(_case(reference=None))

    assert report["metrics"]["faithfulness"]["score"] == 0.9
    assert report["metrics"]["context_recall"]["status"] == "not_applicable"
    assert recall.samples == []
    assert report["passed"] is True


@pytest.mark.asyncio
async def test_ragas_fails_grounding_when_retrieval_context_is_empty():
    case = _case()
    case = BlogEvaluationCase(
        case_id=case.case_id,
        brief=case.brief,
        actual_output=case.actual_output,
        retrieval_contexts=[],
        reference_output=case.reference_output,
        brand_profile=case.brand_profile,
    )
    evaluator = RagasGroundingEvaluator(
        metrics=[RagasMetricBinding("faithfulness", FakeRagasMetric(1.0), threshold=0.8)],
        sample_factory=lambda payload: payload,
    )

    report = await evaluator.evaluate(case)

    assert report["passed"] is False
    assert report["metrics"]["faithfulness"]["score"] == 0.0
    assert report["metrics"]["faithfulness"]["status"] == "missing_context"


def test_batch_summary_reports_average_and_pass_rate_per_metric():
    results = [
        {
            "brand": {
                "metrics": {
                    "tone": {"score": 0.9, "passed": True},
                    "cta": {"score": 0.6, "passed": False},
                }
            },
            "ragas": {
                "metrics": {
                    "faithfulness": {"score": 0.8, "passed": True},
                    "context_recall": {"score": None, "passed": None},
                }
            },
        },
        {
            "brand": {
                "metrics": {
                    "tone": {"score": 0.7, "passed": False},
                    "cta": {"score": 0.8, "passed": True},
                }
            },
            "ragas": {"metrics": {"faithfulness": {"score": 0.6, "passed": False}}},
        },
    ]

    summary = summarize_metrics(results)

    assert summary["brand"]["tone"] == {
        "evaluated": 2,
        "average_score": 0.8,
        "passed": 1,
        "pass_rate": 0.5,
    }
    assert summary["ragas"]["faithfulness"]["average_score"] == 0.7
    assert "context_recall" not in summary["ragas"]


def test_markdown_report_contains_both_evaluation_layers():
    summary = {
        "model": "qwen3.5-2b",
        "evaluated": 1,
        "passed": 0,
        "pass_rate": 0.0,
        "missing_retrieval_contexts": 0,
        "metrics": {
            "brand": {
                "tone": {
                    "average_score": 0.8,
                    "passed": 1,
                    "evaluated": 1,
                    "pass_rate": 1.0,
                }
            },
            "ragas": {
                "faithfulness": {
                    "average_score": 0.6,
                    "passed": 0,
                    "evaluated": 1,
                    "pass_rate": 0.0,
                }
            },
        },
    }

    report = render_report(summary)

    assert "| brand | tone | 0.800 | 1/1 | 100% |" in report
    assert "| ragas | faithfulness | 0.600 | 0/1 | 0% |" in report
