"""Evaluate the brand-voice pipeline with the public TSS article rating sheet.

The sheet supplies article URLs, categories, human ratings, forbidden terms, and
preferred terms. This script fetches the sheet and article bodies, trains the
existing deterministic BrandVoiceService profile from high-rated samples, then
scores every article and compares automated scores with the human ratings.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import html
import json
import math
import random
import re
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings  # noqa: E402
from app.schemas.document import (  # noqa: E402
    AudiencePersona,
    BrandIdentity,
    BrandVoiceEvaluateRequest,
    TrainBrandVoiceRequest,
)
from app.services.brand_voice_service import BrandVoiceService  # noqa: E402


DEFAULT_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "14U0tqAnixw7RHdnFUIUH_V3Wa4pJDakYbZPVjp1CBDU/export?format=csv"
)


@dataclass(frozen=True)
class SheetRecord:
    stt: int
    link: str
    category: str
    rating: int
    avoid: str
    prefer: str


def stratified_split(
    records: list[SheetRecord],
    train_ratio: float = 0.7,
    seed: int = 42,
) -> tuple[list[SheetRecord], list[SheetRecord]]:
    """Split each category while preserving the high/low rating mix."""
    if not 0 < train_ratio < 1:
        raise ValueError("train_ratio must be between 0 and 1")

    rng = random.Random(seed)
    by_category: dict[str, list[SheetRecord]] = defaultdict(list)
    for record in records:
        by_category[record.category].append(record)

    train: list[SheetRecord] = []
    test: list[SheetRecord] = []
    for category in sorted(by_category):
        category_rows = by_category[category]
        target_test = max(1, len(category_rows) - round(len(category_rows) * train_ratio))
        high = [row for row in category_rows if row.rating >= 4]
        low = [row for row in category_rows if row.rating < 4]
        rng.shuffle(high)
        rng.shuffle(low)

        high_test_count = min(len(high), round(len(high) * (1 - train_ratio)))
        low_test_count = min(len(low), target_test - high_test_count)
        while high_test_count + low_test_count < target_test:
            if low_test_count < len(low):
                low_test_count += 1
            elif high_test_count < len(high):
                high_test_count += 1
            else:
                break

        category_test = high[:high_test_count] + low[:low_test_count]
        test_ids = {row.stt for row in category_test}
        test.extend(category_test)
        train.extend(row for row in category_rows if row.stt not in test_ids)

    return sorted(train, key=lambda row: row.stt), sorted(test, key=lambda row: row.stt)


class NullVectorStore:
    def add_documents(self, texts: list[str], metadatas: list[dict[str, Any]], ids: list[str]) -> None:
        return None

    def query(self, query_text: str, top_k: int = 5, where: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return []

    def get_documents(self, where: dict[str, Any] | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        return []

    def delete_document(self, document_id: str) -> int:
        return 0

    def get_document_ids(self) -> list[str]:
        return []

    def count(self) -> int:
        return 0


class ArticleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self._tag_stack: list[str] = []
        self._skip_depth = 0
        self._title_depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        self._tag_stack.append(tag)
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if tag == "title":
            self._title_depth += 1
        if tag in {"p", "h1", "h2", "h3", "li", "blockquote"}:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title" and self._title_depth:
            self._title_depth -= 1
        if self._tag_stack:
            self._tag_stack.pop()
        if tag in {"p", "h1", "h2", "h3", "li", "blockquote", "article", "main"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self._title_depth:
            self.title = clean_spaces(f"{self.title} {text}")
            return
        if self._skip_depth:
            return
        self._chunks.append(text)

    def article_text(self) -> str:
        text = html.unescape(" ".join(self._chunks))
        text = re.sub(r"\s*\n\s*", "\n", text)
        text = clean_spaces(text)
        return text


def clean_spaces(text: str) -> str:
    return re.sub(r"[ \t\r\f\v]+", " ", text).strip()


def fetch_url(url: str, timeout: int = 30) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; TSSPipelineEvaluator/1.0)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def load_sheet(sheet_url: str) -> list[SheetRecord]:
    payload = fetch_url(sheet_url).decode("utf-8-sig")
    rows = list(csv.reader(payload.splitlines()))
    records: list[SheetRecord] = []
    saw_header = False
    for row in rows:
        if row and row[0] == "STT":
            saw_header = True
            continue
        if not saw_header or len(row) < 4:
            continue
        if not row[0].strip().isdigit() or not row[1].strip() or not row[3].strip().isdigit():
            continue
        records.append(
            SheetRecord(
                stt=int(row[0]),
                link=row[1].strip(),
                category=row[2].strip(),
                rating=int(row[3]),
                avoid=row[5].strip() if len(row) > 5 else "",
                prefer=row[6].strip() if len(row) > 6 else "",
            )
        )
    return records


def extract_article(url: str) -> dict[str, str]:
    raw = fetch_url(url)
    text = raw.decode("utf-8", errors="ignore")
    parser = ArticleTextParser()
    parser.feed(text)
    article = parser.article_text()
    title = parser.title or url.rstrip("/").split("/")[-1].replace("-", " ")
    title, article = clean_extracted_article(title, article)
    return {"title": title, "text": article}


def clean_extracted_article(title: str, article: str) -> tuple[str, str]:
    title = re.sub(
        r"\s+Footer Demo\s+[\u2013-]\s+The Sun Symphony\s*$",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()
    title_start = article.lower().rfind(title.lower())
    if title_start >= 0:
        article = article[title_start:]
    for marker in [
        "Bài viết liên quan",
        "Giới thiệu",
        "THE SUN SYMPHONY. All rights reserved.",
        "Proudly powered by",
    ]:
        marker_index = article.find(marker)
        if marker_index > 500:
            article = article[:marker_index]
            break
    return title, article.strip()


def split_terms(value: str) -> list[str]:
    if not value:
        return []
    terms = re.split(r"[,;\n]+", value)
    return [clean_spaces(term) for term in terms if clean_spaces(term)]


def build_documents(records: list[SheetRecord], article_map: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    documents = []
    for record in records:
        article = article_map.get(record.link, {})
        title, body = clean_extracted_article(
            article.get("title") or f"article-{record.stt}",
            article.get("text") or "",
        )
        if not body.strip():
            continue
        documents.append(
            {
                "document_id": str(record.stt),
                "stt": record.stt,
                "filename": f"{record.stt:02d}-{record.category}.txt",
                "title": title,
                "text": f"# {title}\n\n{body}",
                "rating": record.rating,
                "category": record.category,
                "link": record.link,
                "source_url": record.link,
            }
        )
    return documents


def patch_profile_with_sheet_terms(profile: dict[str, Any], records: list[SheetRecord]) -> None:
    forbidden = []
    preferred = []
    replacements = {}
    for record in records:
        avoid_terms = split_terms(record.avoid)
        prefer_terms = split_terms(record.prefer)
        forbidden.extend(avoid_terms)
        preferred.extend(prefer_terms)
        if avoid_terms and prefer_terms:
            replacements[avoid_terms[0]] = prefer_terms[0]

    vocabulary = profile.setdefault("vocabulary", {})
    vocabulary["forbidden_terms"] = sorted(set(vocabulary.get("forbidden_terms", []) + forbidden))
    vocabulary["preferred_phrases"] = sorted(set(vocabulary.get("preferred_phrases", []) + preferred))
    dictionary = profile.setdefault("dictionary", {})
    dictionary["forbidden_replacements"] = {
        **dictionary.get("forbidden_replacements", {}),
        **replacements,
    }
    allowed = dictionary.get("allowed_terms", [])
    dictionary["allowed_terms"] = sorted(set(allowed + preferred))


async def evaluate_documents(
    service: BrandVoiceService,
    documents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for document in documents:
        result = await service.evaluate(
            BrandVoiceEvaluateRequest(
                channel="blog",
                content_type="blog_post",
                content=document["text"],
                use_llm_judge=False,
            )
        )
        rows.append(
            {
                "stt": document["document_id"],
                "category": document["category"],
                "rating": document["rating"],
                "human_score": rating_to_score(document["rating"]),
                "automated_score": result.overall_score,
                "tone_alignment": result.dimension_scores.get("tone_alignment"),
                "vocabulary": result.dimension_scores.get("vocabulary"),
                "readability": result.dimension_scores.get("readability"),
                "structure": result.dimension_scores.get("structure"),
                "channel_fit": result.dimension_scores.get("channel_fit"),
                "identity_alignment": result.dimension_scores.get("identity_alignment"),
                "persona_fit": result.dimension_scores.get("persona_fit"),
                "writing_fingerprint_fit": result.dimension_scores.get("writing_fingerprint_fit"),
                "link": document["link"],
                "violations": " | ".join(result.violations),
                "recommendations": " | ".join(result.recommendations),
            }
        )
    return rows


def rating_to_score(rating: int) -> int:
    return int(round(((rating - 1) / 4) * 100))


def pearson(left: list[float], right: list[float]) -> float:
    if len(left) < 2 or len(right) < 2:
        return 0.0
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    left_norm = math.sqrt(sum((a - left_mean) ** 2 for a in left))
    right_norm = math.sqrt(sum((b - right_mean) ** 2 for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def rank(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    output = [0.0] * len(values)
    index = 0
    while index < len(indexed):
        end = index + 1
        while end < len(indexed) and indexed[end][1] == indexed[index][1]:
            end += 1
        avg_rank = (index + end - 1) / 2 + 1
        for original_index, _ in indexed[index:end]:
            output[original_index] = avg_rank
        index = end
    return output


def roc_auc(rows: list[dict[str, Any]], positive_rating: int = 4) -> float:
    positives = [float(row["automated_score"]) for row in rows if int(row["rating"]) >= positive_rating]
    negatives = [float(row["automated_score"]) for row in rows if int(row["rating"]) < positive_rating]
    if not positives or not negatives:
        return 0.0
    wins = 0.0
    for pos in positives:
        for neg in negatives:
            if pos > neg:
                wins += 1
            elif pos == neg:
                wins += 0.5
    return wins / (len(positives) * len(negatives))


def best_threshold(rows: list[dict[str, Any]], positive_rating: int = 4) -> tuple[float, float]:
    scores = sorted({float(row["automated_score"]) for row in rows})
    candidates = [(scores[i] + scores[i + 1]) / 2 for i in range(len(scores) - 1)]
    candidates.extend([scores[0] - 0.01, scores[-1] + 0.01])
    best = max(candidates, key=lambda threshold: accuracy(rows, threshold, positive_rating))
    return round(best, 2), round(accuracy(rows, best, positive_rating), 4)


def accuracy(rows: list[dict[str, Any]], threshold: float, positive_rating: int = 4) -> float:
    correct = 0
    for row in rows:
        expected = int(row["rating"]) >= positive_rating
        predicted = float(row["automated_score"]) >= threshold
        correct += int(expected == predicted)
    return correct / max(1, len(rows))


def summarize(records: list[SheetRecord], documents: list[dict[str, Any]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    human = [float(row["human_score"]) for row in rows]
    auto = [float(row["automated_score"]) for row in rows]
    by_category = {}
    for category in sorted({row["category"] for row in rows}):
        category_rows = [row for row in rows if row["category"] == category]
        by_category[category] = {
            "count": len(category_rows),
            "human_rating_avg": round(sum(int(row["rating"]) for row in category_rows) / len(category_rows), 2),
            "automated_score_avg": round(sum(float(row["automated_score"]) for row in category_rows) / len(category_rows), 2),
            "writing_fingerprint_avg": round(
                sum(float(row["writing_fingerprint_fit"]) for row in category_rows) / len(category_rows),
                2,
            ),
        }

    threshold, threshold_accuracy = best_threshold(rows)
    return {
        "sheet_records": len(records),
        "articles_fetched": len(documents),
        "training_articles": sum(1 for document in documents if int(document["rating"]) >= 4),
        "rating_counts": dict(sorted(Counter(record.rating for record in records).items())),
        "category_counts": dict(sorted(Counter(record.category for record in records).items())),
        "automated_score_avg": round(sum(auto) / max(1, len(auto)), 2),
        "human_score_avg": round(sum(human) / max(1, len(human)), 2),
        "pearson_rating_correlation": round(pearson(human, auto), 4),
        "spearman_rating_correlation": round(pearson(rank(human), rank(auto)), 4),
        "mean_absolute_error": round(sum(abs(a - b) for a, b in zip(auto, human)) / max(1, len(rows)), 2),
        "roc_auc_rating_4_plus": round(roc_auc(rows), 4),
        "best_threshold_rating_4_plus": threshold,
        "accuracy_at_best_threshold": threshold_accuracy,
        "by_category": by_category,
        "top_false_positives": [
            row for row in sorted(rows, key=lambda item: float(item["automated_score"]), reverse=True)
            if int(row["rating"]) <= 2
        ][:5],
        "top_false_negatives": [
            row for row in sorted(rows, key=lambda item: float(item["automated_score"]))
            if int(row["rating"]) >= 4
        ][:5],
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# TSS Pipeline Evaluation",
        "",
        f"- Sheet records: {summary['sheet_records']}",
        f"- Articles fetched: {summary['articles_fetched']}",
        f"- Training articles (rating >= 4): {summary['training_articles']}",
        f"- Automated score average: {summary['automated_score_avg']}",
        f"- Human normalized score average: {summary['human_score_avg']}",
        f"- Pearson correlation: {summary['pearson_rating_correlation']}",
        f"- Spearman correlation: {summary['spearman_rating_correlation']}",
        f"- ROC-AUC for rating >= 4: {summary['roc_auc_rating_4_plus']}",
        f"- Best threshold for rating >= 4: {summary['best_threshold_rating_4_plus']}",
        f"- Accuracy at best threshold: {summary['accuracy_at_best_threshold']}",
        "",
        "## By Category",
        "",
        "| Category | Count | Human Avg | Automated Avg | Fingerprint Avg |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for category, row in summary["by_category"].items():
        lines.append(
            f"| {category} | {row['count']} | {row['human_rating_avg']} | "
            f"{row['automated_score_avg']} | {row['writing_fingerprint_avg']} |"
        )
    lines.extend(["", "## Interpretation", ""])
    if summary["spearman_rating_correlation"] < 0.2:
        lines.append(
            "The current heuristic evaluator is weakly aligned with the sheet's human 1-5 ratings. "
            "Use the ratings as supervised calibration data before treating automated scores as quality labels."
        )
    else:
        lines.append(
            "The current heuristic evaluator shows some alignment with human ratings, but should still be calibrated "
            "against category-specific editorial criteria before production use."
        )
    path.write_text("\n".join(lines), encoding="utf-8")


async def run(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    records = load_sheet(args.sheet_url)
    train_records, test_records = stratified_split(
        records, train_ratio=args.train_ratio, seed=args.seed
    )
    article_cache_path = output_dir / "article_texts.json"
    article_map: dict[str, dict[str, str]] = {}
    if args.reuse_cache and article_cache_path.exists():
        article_map = json.loads(article_cache_path.read_text(encoding="utf-8"))
    for index, record in enumerate(records, 1):
        if record.link in article_map and article_map[record.link].get("text"):
            continue
        article_map[record.link] = extract_article(record.link)
        if args.sleep_seconds:
            time.sleep(args.sleep_seconds)
        print(f"Fetched {index}/{len(records)}: {record.link}", flush=True)

    documents = build_documents(records, article_map)
    train_ids = {record.stt for record in train_records}
    test_ids = {record.stt for record in test_records}
    training_documents = [
        document for document in documents
        if int(document["stt"]) in train_ids and int(document["rating"]) >= args.train_min_rating
    ]
    if not training_documents:
        raise RuntimeError("No high-rated documents were available for profile training.")

    settings = Settings(
        BRAND_VOICE_PROFILE_PATH=str(output_dir / "brand_voice_profile.json"),
        BRAND_VOICE_DATASET_DIR=str(output_dir / "brand_voice_dataset"),
        DEBUG=False,
    )
    service = BrandVoiceService(NullVectorStore(), settings)
    analysis = service._fallback_analysis(training_documents)
    profile = service._build_profile(
        analysis=analysis,
        documents=training_documents,
        company_name="The Sun Symphony",
        request=TrainBrandVoiceRequest(
            company_name="The Sun Symphony",
            min_documents=1,
            max_documents=min(30, len(training_documents)),
            target_audience="Người học thanh nhạc cần nền tảng đúng, tự tin và phát triển bền vững.",
            brand_values=["học đúng từ đầu", "nội lực", "lộ trình cá nhân hóa", "tự tin"],
            brand_identity=BrandIdentity(
                mission="Giúp học viên xây dựng nền tảng thanh nhạc đúng và phát triển giọng hát bền vững.",
                positioning="Trung tâm thanh nhạc chuyên sâu, nhấn mạnh kỹ thuật đúng và nội lực.",
                personality_traits=["chuyên sâu", "khích lệ", "rõ ràng", "có phương pháp"],
                differentiators=["lộ trình cá nhân hóa", "nền tảng kỹ thuật", "kết nối nội lực"],
            ),
            audience_personas=[
                AudiencePersona(
                    name="Người học thanh nhạc",
                    priorities=["học đúng từ đầu", "tự tin", "giải quyết vấn đề từ gốc rễ"],
                    knowledge_level="novice",
                    tone_adjustment="Rõ ràng, động viên, tránh hứa hẹn học nhanh.",
                )
            ],
            channels=["blog"],
        ),
    )
    patch_profile_with_sheet_terms(profile, records)
    profile_path = Path(settings.BRAND_VOICE_PROFILE_PATH)
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")

    test_documents = [document for document in documents if int(document["stt"]) in test_ids]
    rows = await evaluate_documents(service, test_documents)
    summary = summarize(test_records, test_documents, rows)
    summary["training_articles"] = len(training_documents)
    summary["dataset"] = {
        "total": len(records),
        "train": len(train_records),
        "test": len(test_records),
        "profile_training_articles": len(training_documents),
        "train_ratio": args.train_ratio,
        "seed": args.seed,
    }

    (output_dir / "sheet_records.json").write_text(
        json.dumps([record.__dict__ for record in records], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "article_texts.json").write_text(json.dumps(article_map, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "split_manifest.json").write_text(
        json.dumps(
            {
                "train": [record.__dict__ for record in train_records],
                "test": [record.__dict__ for record in test_records],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    test_topics = [
        {
            "stt": document["stt"],
            "category": document["category"],
            "title": document["title"],
            "source_url": document["source_url"],
        }
        for document in test_documents[:args.generated_count]
    ]
    (output_dir / "generation_topics.json").write_text(
        json.dumps(test_topics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(output_dir / "evaluation_rows.csv", rows)
    write_report(output_dir / "report.md", summary)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheet-url", default=DEFAULT_SHEET_URL)
    parser.add_argument("--output-dir", type=Path, default=Path("data/eval/tss_pipeline"))
    parser.add_argument("--train-min-rating", type=int, default=4)
    parser.add_argument("--train-ratio", type=float, default=0.7)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--generated-count", type=int, default=10)
    parser.add_argument("--no-reuse-cache", action="store_false", dest="reuse_cache")
    parser.set_defaults(reuse_cache=True)
    parser.add_argument("--sleep-seconds", type=float, default=0.1)
    return parser


def main() -> None:
    summary = asyncio.run(run(build_parser().parse_args()))
    print(json.dumps(summary, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
