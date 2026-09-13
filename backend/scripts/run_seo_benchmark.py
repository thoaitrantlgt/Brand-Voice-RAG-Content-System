"""Run the fixed Content SEO V2 benchmark and report calibration readiness."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.seo_evaluation_service import SeoEvaluationService  # noqa: E402

DEFAULT_DATASET = BACKEND_ROOT / "evaluation" / "seo_v1_cases.json"


def load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(cases, list) or len(cases) < 25:
        raise ValueError("SEO benchmark requires at least 25 fixed cases")
    for case in cases:
        repeated = str(case.get("content_suffix_repeat") or "")
        if repeated:
            case["content"] = str(case["content"]) + repeated * 20 + "\n\n## Theo dõi\n\nDừng khi khó chịu."
    return cases


def predicted_labels(result: dict[str, Any]) -> set[str]:
    codes = {str(item.get("code")) for item in result.get("checks", []) if item.get("status") == "needs_attention"}
    fields = {str(item.get("field")) for item in result.get("field_issues", [])}
    labels = set(codes)
    if "seo_title" in fields:
        labels.add("title_issue")
    if "meta_description" in fields:
        labels.add("meta_issue")
    for annotation in result.get("annotations", []):
        reason = str(annotation.get("reason") or "").casefold()
        if "quá dài" in reason:
            labels.add("long_paragraph")
    return labels


def false_positive_rate(rows: list[dict[str, Any]], expected_label: str, predicted_label: str) -> float | None:
    negatives = [row for row in rows if expected_label not in row["expected_labels"]]
    if not negatives:
        return None
    return sum(predicted_label in row["predicted_labels"] for row in negatives) / len(negatives)


def rank(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    index = 0
    while index < len(order):
        end = index + 1
        while end < len(order) and values[order[end]] == values[order[index]]:
            end += 1
        average_rank = (index + 1 + end) / 2
        for position in order[index:end]:
            ranks[position] = average_rank
        index = end
    return ranks


def spearman(left: list[float], right: list[float]) -> float | None:
    if len(left) < 3 or len(left) != len(right):
        return None
    ranked_left, ranked_right = rank(left), rank(right)
    left_mean, right_mean = mean(ranked_left), mean(ranked_right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(ranked_left, ranked_right, strict=True))
    denominator = (
        sum((a - left_mean) ** 2 for a in ranked_left)
        * sum((b - right_mean) ** 2 for b in ranked_right)
    ) ** 0.5
    return numerator / denominator if denominator else None


def run_benchmark(cases: list[dict[str, Any]]) -> dict[str, Any]:
    service = SeoEvaluationService()
    rows: list[dict[str, Any]] = []
    fabricated_annotations = 0
    human_scores: list[float] = []
    system_scores: list[float] = []
    for case in cases:
        result = service.evaluate(
            content=str(case["content"]),
            brief=dict(case["brief"]),
            seo_title=case.get("seo_title"),
            meta_description=case.get("meta_description"),
            suggested_slug=case.get("suggested_slug"),
            existing_project_blogs=list(case.get("existing_project_blogs") or []),
        )
        labels = predicted_labels(result)
        expected = set(case.get("expected_labels") or [])
        reviews_by_reviewer: dict[str, float] = {}
        for item in case.get("human_reviews", []):
            reviewer_id = str(item.get("reviewer_id") or "").strip()
            if reviewer_id and item.get("score") is not None and reviewer_id not in reviews_by_reviewer:
                reviews_by_reviewer[reviewer_id] = float(item["score"])
        reviews = list(reviews_by_reviewer.values())
        if len(reviews) >= 2:
            human_scores.append(mean(reviews))
            system_scores.append(float(result["score"]))
        fabricated_annotations += sum(
            str(item.get("quote") or "") not in str(case["content"])
            for item in result.get("annotations", [])
        )
        rows.append({
            "case_id": case["case_id"],
            "score": result["score"],
            "expected_labels": sorted(expected),
            "predicted_labels": sorted(labels),
        })

    stuffing_positives = [row for row in rows if "keyword_stuffing" in row["expected_labels"]]
    stuffing_recall = (
        sum("keyword_repetition" in row["predicted_labels"] for row in stuffing_positives) / len(stuffing_positives)
        if stuffing_positives else None
    )
    severe_rows = [row for row in rows if {"title_issue", "meta_issue"} & set(row["expected_labels"])]
    severe_recall = (
        sum(bool({"title_issue", "meta_issue"} & set(row["predicted_labels"])) for row in severe_rows) / len(severe_rows)
        if severe_rows else None
    )
    calibration_ready = len(human_scores) == len(rows)
    mean_absolute_error = (
        mean(abs(system - human) for system, human in zip(system_scores, human_scores, strict=True))
        if calibration_ready
        else None
    )
    return {
        "metric_schema_version": "content_seo_v2",
        "case_count": len(rows),
        "human_reviewed_case_count": len(human_scores),
        "calibration_status": "ready" if calibration_ready else "pending_two_human_reviews",
        "spearman_human_score": (
            spearman(system_scores, human_scores) if calibration_ready else None
        ),
        "mean_absolute_error": mean_absolute_error,
        "keyword_stuffing_recall": stuffing_recall,
        "keyword_stuffing_false_positive_rate": false_positive_rate(rows, "keyword_stuffing", "keyword_repetition"),
        "severe_title_meta_recall": severe_recall,
        "fabricated_annotation_count": fabricated_annotations,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_benchmark(load_cases(args.dataset))
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
