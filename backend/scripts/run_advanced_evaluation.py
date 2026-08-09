"""Evaluate generated TSS blogs with DeepEval brand metrics and Ragas grounding metrics."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.evaluation.deepeval_brand import DeepEvalBrandEvaluator, build_brand_metrics
from app.evaluation.models import BlogEvaluationCase
from app.evaluation.providers import create_deepeval_openai_model, create_ragas_openai_stack
from app.evaluation.ragas_grounding import RagasGroundingEvaluator, build_ragas_metrics


def _contexts(row: dict[str, Any]) -> list[str]:
    contexts = []
    for item in row.get("retrieved_contexts") or []:
        text = item.get("text", "") if isinstance(item, dict) else str(item)
        if str(text).strip():
            contexts.append(str(text))
    return contexts


def build_case(
    row: dict[str, Any], article_map: dict[str, dict[str, str]], profile: dict[str, Any]
) -> BlogEvaluationCase:
    source_url = str(row.get("source_url") or "")
    reference = article_map.get(source_url, {}).get("text") or row.get("reference_output")
    brief = row.get("brief") or {
        "topic": row.get("title", ""),
        "category": row.get("category", ""),
        "audience": "Người học thanh nhạc",
        "objective": "Cung cấp hướng dẫn hữu ích và chính xác",
        "must_cover": [],
        "must_avoid": [],
    }
    return BlogEvaluationCase(
        case_id=f"tss-{row.get('stt', row.get('title', 'unknown'))}",
        brief=brief,
        actual_output=str(row.get("content") or row.get("actual_output") or ""),
        retrieval_contexts=_contexts(row),
        reference_output=str(reference) if reference else None,
        brand_profile=profile,
        metadata={"category": row.get("category"), "source_url": source_url},
    )


def summarize_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for framework in ("brand", "ragas"):
        metric_rows: dict[str, list[dict[str, Any]]] = {}
        for item in results:
            for name, metric in item.get(framework, {}).get("metrics", {}).items():
                if metric.get("score") is not None:
                    metric_rows.setdefault(name, []).append(metric)
        summary[framework] = {
            name: {
                "evaluated": len(values),
                "average_score": round(
                    sum(float(value["score"]) for value in values) / len(values), 4
                ),
                "passed": sum(value.get("passed") is True for value in values),
                "pass_rate": round(
                    sum(value.get("passed") is True for value in values) / len(values), 4
                ),
            }
            for name, values in metric_rows.items()
        }
    return summary


def render_report(summary: dict[str, Any]) -> str:
    lines = [
        f"# Advanced Evaluation - {summary['model']}",
        "",
        f"- Evaluated: {summary['evaluated']}",
        f"- Passed: {summary['passed']}",
        f"- Pass rate: {summary['pass_rate']:.0%}",
        f"- Cases missing retrieval contexts: {summary['missing_retrieval_contexts']}",
        "",
        "| Layer | Metric | Average | Passed | Pass rate |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for framework, metrics in summary["metrics"].items():
        for name, metric in metrics.items():
            lines.append(
                f"| {framework} | {name} | {metric['average_score']:.3f} | "
                f"{metric['passed']}/{metric['evaluated']} | {metric['pass_rate']:.0%} |"
            )
    return "\n".join(lines) + "\n"


async def run(args: argparse.Namespace) -> dict[str, Any]:
    os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
    os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")
    rows = json.loads(args.generation_results.read_text(encoding="utf-8"))
    article_map = json.loads((args.dataset_dir / "article_texts.json").read_text(encoding="utf-8"))
    profile = json.loads((args.dataset_dir / "brand_voice_profile.json").read_text(encoding="utf-8"))
    rows = [row for row in rows if row.get("content") and not row.get("error")][: args.limit]

    brand_evaluator = None
    if not args.skip_brand:
        judge = create_deepeval_openai_model(
            model=args.model,
            base_url=args.base_url,
            api_key=args.api_key,
            max_tokens=args.judge_max_tokens,
        )
        brand_evaluator = DeepEvalBrandEvaluator(
            build_brand_metrics(judge, args.brand_threshold),
            metric_delay_seconds=args.metric_delay_seconds,
        )

    ragas_evaluator = None
    if not args.skip_ragas:
        llm, embeddings = create_ragas_openai_stack(
            model=args.model,
            embedding_model=args.embedding_model,
            base_url=args.base_url,
            api_key=args.api_key,
            max_tokens=args.judge_max_tokens,
            embedding_base_url=args.embedding_base_url or args.base_url,
            embedding_api_key=args.embedding_api_key or args.api_key,
        )
        ragas_metrics = build_ragas_metrics(llm, embeddings)
        if args.ragas_metrics:
            selected = set(args.ragas_metrics)
            ragas_metrics = [metric for metric in ragas_metrics if metric.name in selected]
        ragas_evaluator = RagasGroundingEvaluator(
            ragas_metrics,
            metric_delay_seconds=args.metric_delay_seconds,
        )

    results = []
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        case = build_case(row, article_map, profile)
        item: dict[str, Any] = {
            "case_id": case.case_id,
            "title": case.brief.get("topic"),
            "category": case.metadata.get("category"),
            "retrieved_context_count": len(case.retrieval_contexts),
            "has_reference": bool(case.reference_output),
        }
        if brand_evaluator:
            try:
                item["brand"] = brand_evaluator.evaluate(case)
            except Exception as exc:
                item["brand"] = {"framework": "deepeval", "passed": False, "error": str(exc)}
        if ragas_evaluator:
            try:
                item["ragas"] = await ragas_evaluator.evaluate(case)
            except Exception as exc:
                item["ragas"] = {"framework": "ragas", "passed": False, "error": str(exc)}
        reports = [item[key] for key in ("brand", "ragas") if key in item]
        item["passed"] = bool(reports) and all(report["passed"] for report in reports)
        results.append(item)
        (args.output_dir / "results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    summary = {
        "model": args.model,
        "evaluated": len(results),
        "passed": sum(bool(item["passed"]) for item in results),
        "pass_rate": round(
            sum(bool(item["passed"]) for item in results) / max(1, len(results)), 4
        ),
        "missing_retrieval_contexts": sum(
            item["retrieved_context_count"] == 0 for item in results
        ),
        "metrics": summarize_metrics(results),
        "results_path": str(args.output_dir / "results.json"),
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / "report.md").write_text(render_report(summary), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generation-results", type=Path, default=Path("data/eval/tss_generation_qwen3_5_2b/generation_results.json"))
    parser.add_argument("--dataset-dir", type=Path, default=Path("data/eval/tss_pipeline_v2"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/eval/advanced_qwen3_5_2b"))
    parser.add_argument("--model", default=os.getenv("EVAL_MODEL", "qwen3.5-2b"))
    parser.add_argument("--embedding-model", default=os.getenv("EVAL_EMBEDDING_MODEL", "text-embedding-nomic-embed-text-v1.5"))
    parser.add_argument("--base-url", default=os.getenv("EVAL_API_BASE", "http://127.0.0.1:1234/v1"))
    parser.add_argument("--api-key", default=os.getenv("EVAL_API_KEY", "lm-studio"))
    parser.add_argument("--embedding-base-url", default=os.getenv("EVAL_EMBEDDING_API_BASE"))
    parser.add_argument("--embedding-api-key", default=os.getenv("EVAL_EMBEDDING_API_KEY"))
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--brand-threshold", type=float, default=0.8)
    parser.add_argument("--judge-max-tokens", type=int, default=2048)
    parser.add_argument("--metric-delay-seconds", type=float, default=0)
    parser.add_argument(
        "--ragas-metrics",
        nargs="+",
        choices=[
            "faithfulness",
            "response_relevancy",
            "context_precision",
            "context_recall",
            "factual_correctness",
        ],
    )
    parser.add_argument("--skip-brand", action="store_true")
    parser.add_argument("--skip-ragas", action="store_true")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
