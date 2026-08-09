import re
from collections.abc import Callable
from typing import Any


class QualityGate:
    BOILERPLATE = ("footer demo", "navigation", "breadcrumb")
    REQUIREMENT_FILLER = {
        "cách", "hướng", "dẫn", "nội", "dung", "phần", "vấn", "đề",
        "kỹ", "thuật", "tư", "thế", "và", "của", "cho", "với", "về", "khi",
    }

    def evaluate(
        self,
        content: str,
        *,
        dimension_scores: dict[str, int] | None = None,
        forbidden_terms: list[str] | None = None,
        project_leakage: bool = False,
        must_cover: list[str] | None = None,
        must_avoid: list[str] | None = None,
        target_length: int | None = None,
    ) -> dict[str, Any]:
        scores = dimension_scores or {}
        violations: list[dict[str, Any]] = []
        h1_count = len(re.findall(r"(?m)^#\s+\S", content))
        if h1_count != 1:
            violations.append({"code": "invalid_h1_count", "actual": h1_count, "expected": 1})

        lowered = content.casefold()
        matched_forbidden = sorted(
            {term for term in (forbidden_terms or []) if term.casefold() in lowered}
        )
        if matched_forbidden:
            violations.append({"code": "forbidden_term", "terms": matched_forbidden})

        boilerplate = [term for term in self.BOILERPLATE if term in lowered]
        if boilerplate:
            violations.append({"code": "boilerplate_detected", "terms": boilerplate})

        thresholds = {"brand": 80, "style": 80, "fingerprint": 60}
        for dimension, threshold in thresholds.items():
            value = scores.get(dimension, 0)
            if value < threshold:
                violations.append(
                    {
                        "code": f"{dimension}_below_threshold",
                        "actual": value,
                        "threshold": threshold,
                    }
                )
        if project_leakage:
            violations.append({"code": "project_leakage"})
        missing = [
            item
            for item in (must_cover or [])
            if not self._requirement_is_covered(item, lowered)
        ]
        if missing:
            violations.append({"code": "missing_required_content", "items": missing})
        avoided = [item for item in (must_avoid or []) if item.casefold() in lowered]
        if avoided:
            violations.append({"code": "brief_avoidance_violation", "items": avoided})
        if target_length:
            word_count = len(re.findall(r"\b\w+\b", content, re.UNICODE))
            minimum = round(target_length * 0.6)
            maximum = round(target_length * 1.4)
            if word_count < minimum or word_count > maximum:
                violations.append(
                    {"code": "target_length_mismatch", "actual": word_count, "minimum": minimum, "maximum": maximum}
                )

        return {
            "passed": not violations,
            "dimension_scores": scores,
            "violations": violations,
        }

    @classmethod
    def _requirement_is_covered(cls, requirement: str, lowered_content: str) -> bool:
        normalized = requirement.casefold().strip()
        if not normalized or normalized in lowered_content:
            return True
        tokens = re.findall(r"\b\w+\b", normalized, re.UNICODE)
        meaningful = [token for token in tokens if token not in cls.REQUIREMENT_FILLER]
        checked = meaningful or tokens
        if not checked:
            return True
        return all(re.search(rf"\b{re.escape(token)}\b", lowered_content) for token in checked)


class GenerationQualityLoop:
    def __init__(
        self,
        *,
        evaluate: Callable[[str], dict[str, Any]],
        rewrite: Callable[[str, list[str]], str],
        max_rewrites: int = 2,
    ):
        self.evaluate = evaluate
        self.rewrite = rewrite
        self.max_rewrites = max_rewrites

    def run(self, generate: Callable[[], str]) -> dict[str, Any]:
        content = generate()
        attempts: list[dict[str, Any]] = []
        rewrite_count = 0

        while True:
            report = self.evaluate(content)
            attempts.append({"content": content, "quality_report": report})
            if report.get("passed") or rewrite_count >= self.max_rewrites:
                return {
                    "content": content,
                    "quality_report": report,
                    "rewrite_count": rewrite_count,
                    "attempts": attempts,
                }
            codes = [str(item.get("code")) for item in report.get("violations", [])]
            content = self.rewrite(content, codes)
            rewrite_count += 1
