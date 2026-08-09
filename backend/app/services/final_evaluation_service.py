"""Structured final evaluation with model explanations and verified text locations."""
from __future__ import annotations

import json
import re
from statistics import mean
from typing import Any

from app.agents.llm_factory import LLMFactory
from app.core.config import AIProvider, RunMode, Settings
from app.core.logging import logger


class FinalEvaluationService:
    """Explain fixed runtime scores and locate weak passages in the final article."""

    MAX_ANNOTATIONS = 20
    MAX_QUOTE_CHARS = 160

    def __init__(self, settings: Settings, llm: Any | None = None) -> None:
        self.settings = settings
        self._llm = llm

    def evaluate(
        self,
        *,
        content: str,
        brief: dict[str, Any],
        quality_report: dict[str, Any],
        profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        scores = self._fixed_scores(quality_report)
        base = {
            "status": "evaluated",
            "provider": self.settings.FINAL_JUDGE_PROVIDER.value,
            "model": self.settings.FINAL_JUDGE_MODEL,
        }
        if not self.settings.FINAL_JUDGE_ENABLED:
            dimensions = self._fallback_dimensions(scores)
            return {
                **base,
                "status": "disabled",
                "overall_score": self._overall_score(dimensions),
                "passed": bool(quality_report.get("passed")),
                "summary": "Final model evaluation is disabled.",
                "dimensions": dimensions,
                "annotations": [],
            }

        try:
            llm = self._llm or self._create_llm()
            prompt = self._build_prompt(content, brief, quality_report, profile, scores)
            response = llm.call([{"role": "user", "content": prompt}])
            payload = self._parse_json(str(response))
            dimensions = self._normalize_dimensions(payload.get("dimensions"), scores)
            annotation_scores = {
                item["metric"]: int(item["score"])
                for item in dimensions
                if item.get("score") is not None
            }
            annotations, unmapped = self._normalize_annotations(
                payload.get("annotations"), content, annotation_scores
            )
            return {
                **base,
                "overall_score": self._overall_score(dimensions),
                "passed": bool(quality_report.get("passed")),
                "summary": str(payload.get("summary") or "Đã đánh giá bài viết cuối cùng."),
                "dimensions": dimensions,
                "annotations": annotations,
                "unmapped_annotation_count": unmapped,
            }
        except Exception as exc:
            logger.warning("Final model evaluation failed | error={}", exc)
            dimensions = self._fallback_dimensions(scores)
            return {
                **base,
                "status": "error",
                "overall_score": self._overall_score(dimensions),
                "passed": bool(quality_report.get("passed")),
                "summary": "Không thể chạy model đánh giá cuối cùng.",
                "dimensions": dimensions,
                "annotations": [],
                "error": str(exc),
            }

    def _create_llm(self) -> Any:
        provider = self.settings.FINAL_JUDGE_PROVIDER
        if provider in {AIProvider.OPENAI, AIProvider.VLLM}:
            from openai import OpenAI

            if provider == AIProvider.VLLM:
                api_key = self.settings.FINAL_JUDGE_API_KEY or self.settings.VLLM_API_KEY
                base_url = self.settings.FINAL_JUDGE_API_BASE or self.settings.VLLM_BASE_URL
            else:
                api_key = self.settings.FINAL_JUDGE_API_KEY or self.settings.OPENAI_API_KEY
                base_url = self.settings.FINAL_JUDGE_API_BASE or self.settings.OPENAI_API_BASE
            if not base_url:
                raise ValueError("FINAL_JUDGE_API_BASE is required for the OpenAI-compatible judge")
            client = OpenAI(api_key=api_key or "local-judge", base_url=base_url)
            model = self.settings.FINAL_JUDGE_MODEL
            inject_nothink = provider == AIProvider.OPENAI and (
                "127.0.0.1" in base_url or "localhost" in base_url
            )

            class OpenAICompatibleJudge:
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

            return OpenAICompatibleJudge()

        updates: dict[str, Any] = {
            "RUN_MODE": RunMode.CLOUD,
            "AI_PROVIDER": provider,
        }
        if provider == AIProvider.GOOGLE:
            updates["GOOGLE_API_KEY"] = (
                self.settings.FINAL_JUDGE_API_KEY or self.settings.GOOGLE_API_KEY
            )
        judge_settings = self.settings.model_copy(update=updates)
        return LLMFactory(judge_settings).create(self.settings.FINAL_JUDGE_MODEL)

    @staticmethod
    def _fixed_scores(quality_report: dict[str, Any]) -> dict[str, int]:
        return {
            str(name): max(0, min(100, int(value)))
            for name, value in (quality_report.get("dimension_scores") or {}).items()
        }

    @staticmethod
    def _overall_score(dimensions: list[dict[str, Any]]) -> int:
        values = [int(item["score"]) for item in dimensions if item.get("score") is not None]
        return round(mean(values)) if values else 0

    def _build_prompt(
        self,
        content: str,
        brief: dict[str, Any],
        quality_report: dict[str, Any],
        profile: dict[str, Any] | None,
        scores: dict[str, int],
    ) -> str:
        profile_summary = {}
        if profile:
            selected_persona = (quality_report.get("profile_evaluation") or {}).get(
                "selected_persona"
            )
            profile_summary = {
                "brand_identity": profile.get("brand_identity", {}),
                "tone": profile.get("tone", {}),
                "audience_personas": (
                    [selected_persona]
                    if isinstance(selected_persona, dict)
                    else (profile.get("audience_personas") or [])[:1]
                ),
                "vocabulary": profile.get("vocabulary", {}),
                "rubrics": (profile.get("rubrics") or [])[:6],
            }
        evaluation_context = {
            "brief": brief,
            "fixed_scores": scores,
            "metric_contract": {
                "brand": "Hard gate >=80; tone, vocabulary và brand identity.",
                "style": "Hard gate >=80; deterministic style, structure và readability.",
                "fingerprint": "Hard gate >=60; sentence rhythm, vocabulary fingerprint và perspective.",
                "persona": "Informational only; không phải hard gate hiện tại.",
            },
            "hard_gate_passed": bool(quality_report.get("passed")),
            "violations": quality_report.get("violations") or [],
            "profile_evaluation": quality_report.get("profile_evaluation") or {},
            "profile": profile_summary,
        }
        metric_names = list(scores)
        return (
            "Bạn là reviewer cuối cùng của một bài blog tiếng Việt. "
            "Các điểm số đã được hệ thống tính và là bất biến; KHÔNG được thay đổi điểm. "
            "Hãy giải thích ngắn gọn vì sao từng metric có điểm đó và chỉ ra chính xác "
            "những đoạn chưa đạt hoặc còn yếu.\n\n"
            "Quy tắc annotation:\n"
            "- quote phải là MỘT câu hoặc cụm ngắn được sao chép NGUYÊN VĂN từ bài blog, dài 4-160 ký tự.\n"
            "- Chỉ annotation đoạn có vấn đề hoặc cần cải thiện; không highlight đoạn tốt.\n"
            "- Có thể annotation metric đã đạt threshold nếu đoạn cụ thể vẫn có thể viết tốt hơn; phải mô tả đây là cải thiện cục bộ, không gọi toàn metric là thất bại.\n"
            "- Ưu tiên 3-8 annotation có giá trị nhất trên toàn bài, tránh đánh dấu dày đặc.\n"
            "- metric phải thuộc danh sách metric được cung cấp.\n"
            "- severity là error nếu lỗi nghiêm trọng, warning nếu chưa đạt, info nếu chỉ là gợi ý.\n"
            "- Nếu không có đoạn cụ thể cần sửa, trả annotations=[]; không được bịa quote.\n"
            "- Lý do và suggestion viết bằng tiếng Việt, cụ thể và có thể hành động.\n"
            "- Với target_length_mismatch, actual/minimum/maximum đều là SỐ TỪ, không phải số ký tự.\n"
            "- Không gọi persona là lỗi hard gate.\n"
            "- Metric đã đạt threshold phải được giải thích theo hướng ĐẠT, không được gọi là lỗi.\n"
            "- Annotation của metric đã đạt chỉ là warning/info cho đoạn cần cải thiện.\n\n"
            "Trả về đúng một JSON object, không markdown, theo schema:\n"
            "{\n"
            '  "summary": "nhận xét tổng thể",\n'
            '  "dimensions": [\n'
            '    {"metric": "brand", "reason": "lý do cho điểm hiện có"}\n'
            "  ],\n"
            '  "annotations": [\n'
            '    {"quote": "đoạn nguyên văn", "metric": "brand", '
            '"severity": "warning", "reason": "vấn đề", "suggestion": "cách sửa"}\n'
            "  ]\n"
            "}\n\n"
            f"Metric bắt buộc: {json.dumps(metric_names, ensure_ascii=False)}\n"
            f"Evaluation context:\n{json.dumps(evaluation_context, ensure_ascii=False)[:7000]}\n\n"
            f"Bài blog cuối cùng:\n---ARTICLE START---\n{content[:14000]}\n---ARTICLE END---"
        )

    @staticmethod
    def _parse_json(response: str) -> dict[str, Any]:
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", response, re.DOTALL | re.IGNORECASE)
        text = fenced.group(1) if fenced else response
        start = text.find("{")
        end = text.rfind("}")
        candidate = text[start : end + 1] if start >= 0 and end > start else text
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            try:
                from json_repair import loads as repair_loads

                payload = repair_loads(candidate)
            except Exception as exc:
                raise ValueError("Final judge did not return valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("Final judge JSON must be an object")
        return payload

    def _normalize_dimensions(
        self, raw: Any, scores: dict[str, int]
    ) -> list[dict[str, Any]]:
        reasons: dict[str, str] = {}
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    metric = str(item.get("metric") or "")
                    if metric in scores:
                        reasons[metric] = str(item.get("reason") or "").strip()
        elif isinstance(raw, dict):
            for metric, item in raw.items():
                if metric in scores:
                    reasons[metric] = (
                        str(item.get("reason") or "").strip()
                        if isinstance(item, dict)
                        else str(item).strip()
                    )
        return [
            {
                "metric": metric,
                "score": score,
                "threshold": self._threshold(metric),
                "gated": self._threshold(metric) is not None,
                "passed": (
                    score >= self._threshold(metric)
                    if self._threshold(metric) is not None
                    else None
                ),
                "reason": reasons.get(metric) or self._fallback_reason(metric, score),
            }
            for metric, score in scores.items()
        ]

    def _normalize_annotations(
        self, raw: Any, content: str, scores: dict[str, int]
    ) -> tuple[list[dict[str, Any]], int]:
        if not isinstance(raw, list):
            return [], 0
        annotations: list[dict[str, Any]] = []
        unmapped = 0
        occupied: list[tuple[int, int]] = []
        for item in raw[: self.MAX_ANNOTATIONS]:
            if not isinstance(item, dict):
                continue
            quote = str(item.get("quote") or "").strip()
            metric = str(item.get("metric") or "")
            if len(quote) < 4 or len(quote) > self.MAX_QUOTE_CHARS or metric not in scores:
                unmapped += 1
                continue
            threshold = self._threshold(metric)
            start = content.find(quote)
            if start < 0:
                start = content.casefold().find(quote.casefold())
            if start < 0:
                unmapped += 1
                continue
            end = start + len(quote)
            if any(start < used_end and end > used_start for used_start, used_end in occupied):
                continue
            occupied.append((start, end))
            requested_severity = str(item.get("severity") or "warning").casefold()
            if threshold is not None and scores[metric] < threshold:
                severity = "error"
            elif requested_severity == "info":
                severity = "info"
            else:
                severity = "warning"
            line = content.count("\n", 0, start) + 1
            last_newline = content.rfind("\n", 0, start)
            column = start + 1 if last_newline < 0 else start - last_newline
            annotations.append(
                {
                    "quote": content[start:end],
                    "metric": metric,
                    "severity": severity,
                    "reason": str(item.get("reason") or "Cần xem lại đoạn này.").strip(),
                    "suggestion": str(
                        item.get("suggestion")
                        or "Hãy viết lại đoạn này theo lý do đánh giá."
                    ).strip(),
                    "start": start,
                    "end": end,
                    "line": line,
                    "column": column,
                }
            )
        annotations.sort(key=lambda item: int(item["start"]))
        return annotations, unmapped

    def _fallback_dimensions(self, scores: dict[str, int]) -> list[dict[str, Any]]:
        return [
            {
                "metric": metric,
                "score": score,
                "threshold": self._threshold(metric),
                "gated": self._threshold(metric) is not None,
                "passed": (
                    score >= self._threshold(metric)
                    if self._threshold(metric) is not None
                    else None
                ),
                "reason": self._fallback_reason(metric, score),
            }
            for metric, score in scores.items()
        ]

    @staticmethod
    def _threshold(metric: str) -> int | None:
        if metric == "persona":
            return None
        return 60 if metric == "fingerprint" else 80

    @staticmethod
    def _fallback_reason(metric: str, score: int) -> str:
        threshold = FinalEvaluationService._threshold(metric)
        if threshold is None:
            return f"Metric {metric} mang tính tham khảo và hiện không chặn quality gate ({score}/100)."
        state = "đạt ngưỡng" if score >= threshold else "chưa đạt ngưỡng"
        return f"Metric {metric} {state} theo quality gate deterministic ({score}/100)."
