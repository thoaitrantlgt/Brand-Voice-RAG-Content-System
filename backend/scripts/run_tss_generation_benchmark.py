"""Generate and evaluate one held-out TSS topic per category."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings  # noqa: E402
from app.crews.content_crew import ContentCrew  # noqa: E402
from app.rag.vector_store import ChromaVectorStore  # noqa: E402
from app.schemas.document import BrandVoiceEvaluateRequest  # noqa: E402
from app.services.brand_voice_service import BrandVoiceService  # noqa: E402
from app.services.content_service import ContentService  # noqa: E402


DEFAULT_OUTLINE = [
    "## Van de va boi canh",
    "## Nguyen tac va cach thuc hien",
    "## Loi thuong gap va cach sua",
    "## Bai tap hoac buoc hanh dong",
    "## Ket luan",
]


def select_topics(topics: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    selected = []
    seen = set()
    for topic in topics:
        category = topic["category"]
        if category in seen:
            continue
        selected.append(topic)
        seen.add(category)
        if len(selected) >= limit:
            break
    return selected


async def run(args: argparse.Namespace) -> dict[str, Any]:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    dataset_dir = args.dataset_dir
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    topics = json.loads((dataset_dir / "generation_topics.json").read_text(encoding="utf-8"))
    article_map = json.loads((dataset_dir / "article_texts.json").read_text(encoding="utf-8"))
    selected = select_topics(topics, args.count)
    settings = Settings(
        BRAND_VOICE_PROFILE_PATH=str(dataset_dir / "brand_voice_profile.json"),
        PLANNER_MODEL=args.model,
        WRITER_MODEL=args.model,
        EDITOR_MODEL=args.model,
        DEBUG=False,
    )
    store = ChromaVectorStore(settings)
    content_service = ContentService(ContentCrew(settings, store))
    evaluator = BrandVoiceService(store, settings)
    rows = []

    for index, topic in enumerate(selected, 1):
        started = time.perf_counter()
        print(f"Generating {index}/{len(selected)} | {topic['category']} | {topic['title']}", flush=True)
        try:
            generated = await content_service.generate_content(
                keywords=[topic["title"]],
                selected_title=topic["title"],
                outline=DEFAULT_OUTLINE,
                use_web_search=False,
                project_id=args.project,
            )
            content = generated["optimized_content"]
            evaluation = await evaluator.evaluate(
                BrandVoiceEvaluateRequest(
                    content=content,
                    channel="blog",
                    content_type="blog_post",
                    use_llm_judge=False,
                )
            )
            rows.append(
                {
                    **topic,
                    "model": args.model,
                    "seconds": round(time.perf_counter() - started, 1),
                    "word_count": len(content.split()),
                    "h1_count": len(re.findall(r"(?m)^#\s+", content)),
                    "h2_count": len(re.findall(r"(?m)^##\s+", content)),
                    "style_score": generated["style_report"]["style_score"],
                    "brand_score": evaluation.overall_score,
                    "dimension_scores": evaluation.dimension_scores,
                    "violations": evaluation.violations,
                    "recommendations": evaluation.recommendations,
                    "brief": {
                        "topic": topic["title"],
                        "category": topic["category"],
                        "audience": "Người học thanh nhạc",
                        "objective": "Cung cấp hướng dẫn hữu ích và chính xác",
                        "must_cover": [],
                        "must_avoid": [],
                    },
                    "citations": generated.get("citations") or [],
                    "retrieved_contexts": generated.get("retrieved_contexts") or [],
                    "reference_output": article_map.get(topic.get("source_url", ""), {}).get("text"),
                    "passed": evaluation.overall_score >= args.pass_score and not evaluation.violations,
                    "content": content,
                }
            )
        except Exception as exc:
            rows.append({**topic, "model": args.model, "error": str(exc), "passed": False})

        (output_dir / "generation_results.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    successful = [row for row in rows if "brand_score" in row]
    summary = {
        "model": args.model,
        "requested": len(selected),
        "successful": len(successful),
        "pass_score": args.pass_score,
        "passed": sum(bool(row["passed"]) for row in successful),
        "pass_rate": round(sum(bool(row["passed"]) for row in successful) / max(1, len(successful)), 4),
        "average_brand_score": round(sum(row["brand_score"] for row in successful) / max(1, len(successful)), 2),
        "average_style_score": round(sum(row["style_score"] for row in successful) / max(1, len(successful)), 2),
        "average_fingerprint_score": round(
            sum(row["dimension_scores"].get("writing_fingerprint_fit", 0) for row in successful)
            / max(1, len(successful)),
            2,
        ),
        "average_persona_score": round(
            sum(row["dimension_scores"].get("persona_fit", 0) for row in successful)
            / max(1, len(successful)),
            2,
        ),
        "average_seconds": round(sum(row["seconds"] for row in successful) / max(1, len(successful)), 1),
        "by_category": {
            row["category"]: {
                "brand_score": row.get("brand_score"),
                "style_score": row.get("style_score"),
                "fingerprint_score": row.get("dimension_scores", {}).get("writing_fingerprint_fit"),
                "persona_score": row.get("dimension_scores", {}).get("persona_fit"),
                "passed": row["passed"],
                "error": row.get("error"),
            }
            for row in rows
        },
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report = [
        f"# TSS Generation Benchmark - {args.model}",
        "",
        f"- Successful: {summary['successful']}/{summary['requested']}",
        f"- Pass rate: {summary['pass_rate']:.0%}",
        f"- Average brand score: {summary['average_brand_score']}",
        f"- Average style score: {summary['average_style_score']}",
        f"- Average fingerprint score: {summary['average_fingerprint_score']}",
        f"- Average persona score: {summary['average_persona_score']}",
        f"- Average generation time: {summary['average_seconds']} seconds",
        "",
        "| Category | Brand | Style | Fingerprint | Persona | Pass |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for category, metrics in summary["by_category"].items():
        report.append(
            f"| {category} | {metrics['brand_score'] or '-'} | {metrics['style_score'] or '-'} | "
            f"{metrics['fingerprint_score'] or '-'} | {metrics['persona_score'] or '-'} | "
            f"{'yes' if metrics['passed'] else 'no'} |"
        )
    (output_dir / "report.md").write_text("\n".join(report), encoding="utf-8")
    return summary


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=Path("data/eval/tss_pipeline_v2"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/eval/tss_generation_gemini_3_5_flash"))
    parser.add_argument("--model", default="gemini-3.5-flash")
    parser.add_argument("--project", default="tss")
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--pass-score", type=int, default=80)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args)), ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
