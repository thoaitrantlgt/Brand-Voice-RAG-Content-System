from __future__ import annotations

import asyncio
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from app.evaluation.models import BlogEvaluationCase


@dataclass(frozen=True)
class RagasMetricBinding:
    name: str
    metric: Any
    threshold: float
    requires_reference: bool = False


def build_ragas_sample(payload: dict[str, Any]) -> Any:
    try:
        from ragas import SingleTurnSample
    except ImportError as exc:
        raise RuntimeError(
            "Ragas is not installed. Use backend/requirements-eval.txt in an isolated venv."
        ) from exc
    return SingleTurnSample(**payload)


def build_ragas_metrics(llm: Any, embeddings: Any) -> list[RagasMetricBinding]:
    try:
        from ragas.metrics import (
            Faithfulness,
            FactualCorrectness,
            LLMContextPrecisionWithReference,
            LLMContextRecall,
            ResponseRelevancy,
        )
    except ImportError as exc:
        raise RuntimeError(
            "Ragas is not installed. Use backend/requirements-eval.txt in an isolated venv."
        ) from exc

    return [
        RagasMetricBinding("faithfulness", Faithfulness(llm=llm), 0.8),
        RagasMetricBinding(
            "response_relevancy",
            ResponseRelevancy(llm=llm, embeddings=embeddings),
            0.7,
        ),
        RagasMetricBinding(
            "context_precision",
            LLMContextPrecisionWithReference(llm=llm),
            0.7,
            requires_reference=True,
        ),
        RagasMetricBinding(
            "context_recall",
            LLMContextRecall(llm=llm),
            0.7,
            requires_reference=True,
        ),
        RagasMetricBinding(
            "factual_correctness",
            FactualCorrectness(llm=llm, language="vietnamese"),
            0.8,
            requires_reference=True,
        ),
    ]


class RagasGroundingEvaluator:
    def __init__(
        self,
        metrics: Sequence[RagasMetricBinding],
        sample_factory: Callable[[dict[str, Any]], Any] = build_ragas_sample,
        metric_delay_seconds: float = 0,
    ) -> None:
        self.metrics = list(metrics)
        self.sample_factory = sample_factory
        self.metric_delay_seconds = metric_delay_seconds

    async def evaluate(self, case: BlogEvaluationCase) -> dict[str, Any]:
        results: dict[str, Any] = {}
        if not case.retrieval_contexts:
            for binding in self.metrics:
                results[binding.name] = {
                    "score": 0.0,
                    "threshold": binding.threshold,
                    "passed": False,
                    "status": "missing_context",
                }
            return {
                "framework": "ragas",
                "case_id": case.case_id,
                "overall_score": 0.0,
                "passed": False,
                "metrics": results,
            }

        sample = self.sample_factory(case.ragas_payload())
        for index, binding in enumerate(self.metrics):
            if binding.requires_reference and not case.reference_output:
                results[binding.name] = {
                    "score": None,
                    "threshold": binding.threshold,
                    "passed": None,
                    "status": "not_applicable",
                }
                if self.metric_delay_seconds and index < len(self.metrics) - 1:
                    await asyncio.sleep(self.metric_delay_seconds)
                continue
            try:
                score = float(await binding.metric.single_turn_ascore(sample))
            except Exception as exc:
                results[binding.name] = {
                    "score": None,
                    "threshold": binding.threshold,
                    "passed": False,
                    "status": "error",
                    "error": str(exc),
                }
                if self.metric_delay_seconds and index < len(self.metrics) - 1:
                    await asyncio.sleep(self.metric_delay_seconds)
                continue
            if math.isnan(score):
                results[binding.name] = {
                    "score": None,
                    "threshold": binding.threshold,
                    "passed": False,
                    "status": "invalid_score",
                }
                if self.metric_delay_seconds and index < len(self.metrics) - 1:
                    await asyncio.sleep(self.metric_delay_seconds)
                continue
            results[binding.name] = {
                "score": round(score, 4),
                "threshold": binding.threshold,
                "passed": score >= binding.threshold,
                "status": "evaluated",
            }
            if self.metric_delay_seconds and index < len(self.metrics) - 1:
                await asyncio.sleep(self.metric_delay_seconds)

        applicable = [item for item in results.values() if item["score"] is not None]
        required = [
            item for item in results.values() if item.get("status") != "not_applicable"
        ]
        overall = (
            round(sum(float(item["score"]) for item in applicable) / len(applicable), 3)
            if applicable
            else 0.0
        )
        return {
            "framework": "ragas",
            "case_id": case.case_id,
            "overall_score": overall,
            "passed": bool(required) and all(bool(item["passed"]) for item in required),
            "metrics": results,
        }
