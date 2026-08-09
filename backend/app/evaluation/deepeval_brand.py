from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import Any

from app.evaluation.models import BlogEvaluationCase


BRAND_METRIC_SPECS = (
    {
        "name": "tone",
        "criteria": "Đánh giá giọng điệu có gần gũi, hướng dẫn, khích lệ, dễ hiểu và không quá quảng cáo theo brand profile hay không.",
        "steps": [
            "Đọc brand profile và brief trong Input.",
            "Đối chiếu thái độ, mức chuyên môn và mức quảng cáo trong Actual Output.",
            "Chấm mức phù hợp tổng thể và giải thích sai lệch cụ thể.",
        ],
    },
    {
        "name": "addressing",
        "criteria": "Đánh giá cách xưng hô và quan hệ với người đọc có nhất quán với audience và brand profile hay không.",
        "steps": [
            "Xác định audience và cách xưng hô mong muốn từ Input.",
            "Kiểm tra toàn bài có đổi ngôi, xa cách hoặc áp đặt không.",
            "Chấm tính nhất quán của cách xưng hô.",
        ],
    },
    {
        "name": "vocabulary",
        "criteria": "Đánh giá từ vựng, thuật ngữ và cụm từ đặc trưng có đúng brand profile, tự nhiên và dễ hiểu hay không.",
        "steps": [
            "Đối chiếu vocabulary trong brand profile với Actual Output.",
            "Kiểm tra thuật ngữ khó, sáo ngữ, từ cấm và lặp từ khóa.",
            "Chấm mức phù hợp và tự nhiên của từ vựng.",
        ],
    },
    {
        "name": "structure",
        "criteria": "Đánh giá cấu trúc blog, mở bài, heading, chuyển đoạn, danh sách và kết bài có rõ ràng và đúng writing fingerprint hay không.",
        "steps": [
            "Đọc yêu cầu cấu trúc trong Input.",
            "Kiểm tra thứ bậc heading và luồng lập luận của Actual Output.",
            "Chấm khả năng quét, đọc và thực hành theo bài.",
        ],
    },
    {
        "name": "cta",
        "criteria": "Đánh giá CTA có đúng mục tiêu bài, tự nhiên, cụ thể và không quảng cáo quá mức hay không.",
        "steps": [
            "Xác định objective và CTA mong muốn từ Input.",
            "Kiểm tra lời kêu gọi hành động trong Actual Output.",
            "Chấm tính phù hợp, cụ thể và mức độ thương mại.",
        ],
    },
    {
        "name": "brief_adherence",
        "criteria": "Đánh giá bài viết có đáp ứng topic, audience, objective, must_cover, must_avoid và độ dài mục tiêu trong brief hay không.",
        "steps": [
            "Liệt kê từng ràng buộc trong brief.",
            "Đối chiếu từng ràng buộc với Actual Output và phát hiện nội dung trái yêu cầu.",
            "Chấm mức hoàn thành brief, ưu tiên các ràng buộc bắt buộc.",
        ],
    },
    {
        "name": "writing_quality",
        "criteria": "Đánh giá chất lượng viết tổng thể: rõ nghĩa, mạch lạc, hữu ích, không lặp, không máy móc và phù hợp một bài blog hoàn chỉnh.",
        "steps": [
            "Kiểm tra tính rõ nghĩa và liên kết giữa các ý.",
            "Kiểm tra độ hữu ích, tính cụ thể, lỗi lặp và câu máy móc.",
            "Chấm chất lượng xuất bản tổng thể.",
        ],
    },
)


def build_deepeval_test_case(case: BlogEvaluationCase) -> Any:
    try:
        from deepeval.test_case import LLMTestCase
    except ImportError as exc:
        raise RuntimeError(
            "DeepEval is not installed. Use backend/requirements-eval.txt in an isolated venv."
        ) from exc
    return LLMTestCase(
        input=case.input_text(),
        actual_output=case.actual_output,
        expected_output=case.reference_output,
        retrieval_context=case.retrieval_contexts or None,
        metadata={"case_id": case.case_id, **case.metadata},
    )


def build_brand_metrics(model: Any, threshold: float = 0.8) -> list[Any]:
    try:
        from deepeval.metrics import GEval
        from deepeval.test_case import SingleTurnParams
    except ImportError as exc:
        raise RuntimeError(
            "DeepEval is not installed. Use backend/requirements-eval.txt in an isolated venv."
        ) from exc

    return [
        GEval(
            name=spec["name"],
            criteria=spec["criteria"],
            evaluation_steps=spec["steps"],
            evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
            model=model,
            threshold=threshold,
            async_mode=False,
        )
        for spec in BRAND_METRIC_SPECS
    ]


class DeepEvalBrandEvaluator:
    def __init__(
        self,
        metrics: Sequence[Any],
        test_case_factory: Callable[[BlogEvaluationCase], Any] = build_deepeval_test_case,
        metric_delay_seconds: float = 0,
    ) -> None:
        self.metrics = list(metrics)
        self.test_case_factory = test_case_factory
        self.metric_delay_seconds = metric_delay_seconds

    def evaluate(self, case: BlogEvaluationCase) -> dict[str, Any]:
        test_case = self.test_case_factory(case)
        results: dict[str, Any] = {}
        for index, metric in enumerate(self.metrics):
            threshold = float(getattr(metric, "threshold", 0.8))
            try:
                score = float(metric.measure(test_case, _show_indicator=False))
                results[str(metric.name)] = {
                    "score": round(score, 4),
                    "threshold": threshold,
                    "passed": bool(getattr(metric, "success", score >= threshold)),
                    "reason": str(getattr(metric, "reason", "") or ""),
                    "status": "evaluated",
                }
            except Exception as exc:
                results[str(metric.name)] = {
                    "score": None,
                    "threshold": threshold,
                    "passed": False,
                    "reason": "",
                    "status": "error",
                    "error": str(exc),
                }
            if self.metric_delay_seconds and index < len(self.metrics) - 1:
                time.sleep(self.metric_delay_seconds)

        scores = [item["score"] for item in results.values() if item["score"] is not None]
        overall = round(sum(scores) / len(scores), 3) if scores else 0.0
        return {
            "framework": "deepeval",
            "case_id": case.case_id,
            "overall_score": overall,
            "passed": bool(results) and all(item["passed"] for item in results.values()),
            "metrics": results,
        }
