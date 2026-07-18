"""Run same-author vs different-author Writing Fingerprint benchmark.

This script is intentionally deterministic by default: it builds profiles from
the local heuristic extractor and evaluates with ``use_llm_judge=false``.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import random
import re
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings  # noqa: E402
from app.schemas.document import BrandVoiceEvaluateRequest, TrainBrandVoiceRequest  # noqa: E402
from app.services.brand_voice_service import BrandVoiceService  # noqa: E402


@dataclass(frozen=True)
class BenchmarkConfig:
    seed: int = 42
    max_authors: int = 100
    source_posts_per_author: int = 5
    positive_posts_per_author: int = 3
    negative_posts_per_author: int = 5
    min_posts_per_author: int = 8
    negative_sampling: str = "hard"
    use_llm_judge: bool = False
    threshold: float | None = None
    scoring_mode: str = "hybrid"
    stylometry_weight: float = 0.85
    top_char_ngrams: int = 300

    @classmethod
    def from_json(cls, path: Path | None) -> "BenchmarkConfig":
        if not path:
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        allowed = {field.name for field in cls.__dataclass_fields__.values()}
        return cls(**{key: value for key, value in raw.items() if key in allowed})

    def to_json(self) -> dict:
        return {
            "seed": self.seed,
            "max_authors": self.max_authors,
            "source_posts_per_author": self.source_posts_per_author,
            "positive_posts_per_author": self.positive_posts_per_author,
            "negative_posts_per_author": self.negative_posts_per_author,
            "min_posts_per_author": self.min_posts_per_author,
            "negative_sampling": self.negative_sampling,
            "use_llm_judge": self.use_llm_judge,
            "threshold": self.threshold,
            "scoring_mode": self.scoring_mode,
            "stylometry_weight": self.stylometry_weight,
            "top_char_ngrams": self.top_char_ngrams,
        }


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


def load_posts(processed_posts_path: Path) -> dict[str, list[dict[str, Any]]]:
    authors: dict[str, list[dict[str, Any]]] = {}
    with processed_posts_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            post = json.loads(line)
            authors.setdefault(str(post["author_id"]), []).append(post)
    for posts in authors.values():
        posts.sort(key=lambda item: (str(item.get("date", "")), str(item.get("post_id", ""))))
    return authors


def eligible_authors(authors: dict[str, list[dict[str, Any]]], config: BenchmarkConfig) -> list[str]:
    needed = (
        config.source_posts_per_author
        + config.positive_posts_per_author
        + 1
    )
    return [
        author_id
        for author_id, posts in authors.items()
        if len(posts) >= max(config.min_posts_per_author, needed)
    ]


def choose_authors(authors: dict[str, list[dict[str, Any]]], config: BenchmarkConfig) -> list[str]:
    rng = random.Random(config.seed)
    candidates = eligible_authors(authors, config)
    rng.shuffle(candidates)
    return candidates[: config.max_authors]


def split_author_posts(
    posts: list[dict[str, Any]],
    config: BenchmarkConfig,
    rng: random.Random,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    shuffled = posts[:]
    rng.shuffle(shuffled)
    source_end = config.source_posts_per_author
    positive_end = source_end + config.positive_posts_per_author
    return shuffled[:source_end], shuffled[source_end:positive_end]


def negative_author_candidates(
    anchor_author: str,
    selected_authors: list[str],
    authors: dict[str, list[dict[str, Any]]],
    mode: str,
) -> list[str]:
    anchor = authors[anchor_author][0]
    others = [author_id for author_id in selected_authors if author_id != anchor_author]
    if mode != "hard":
        return others

    hard = []
    for author_id in others:
        candidate = authors[author_id][0]
        same_gender = candidate.get("gender") == anchor.get("gender")
        same_job = candidate.get("job") == anchor.get("job")
        close_age = _close_age(anchor.get("age"), candidate.get("age"))
        if same_gender and (same_job or close_age):
            hard.append(author_id)
    return hard or others


def choose_negative_posts(
    anchor_author: str,
    selected_authors: list[str],
    authors: dict[str, list[dict[str, Any]]],
    config: BenchmarkConfig,
    rng: random.Random,
) -> list[dict[str, Any]]:
    candidates = negative_author_candidates(anchor_author, selected_authors, authors, config.negative_sampling)
    rng.shuffle(candidates)
    negatives = []
    candidate_offset = 0
    while candidates and len(negatives) < config.negative_posts_per_author:
        author_id = candidates[candidate_offset % len(candidates)]
        available = [
            post for post in authors[author_id]
            if post.get("post_id") not in {item.get("post_id") for item in negatives}
        ]
        if not available:
            break
        negatives.append(rng.choice(available))
        candidate_offset += 1
    return negatives


def build_profile(
    service: BrandVoiceService,
    author_id: str,
    source_posts: list[dict[str, Any]],
) -> dict[str, Any]:
    documents = [
        {
            "document_id": str(post["post_id"]),
            "filename": f"{post['post_id']}.txt",
            "text": post["text"],
        }
        for post in source_posts
    ]
    analysis = service._fallback_analysis(documents)
    return service._build_profile(
        analysis=analysis,
        documents=documents,
        company_name=f"blogger_{author_id}",
        request=TrainBrandVoiceRequest(
            company_name=f"blogger_{author_id}",
            min_documents=1,
            max_documents=len(documents),
            channels=["blog"],
        ),
    )


FUNCTION_WORDS = {
    "a", "about", "after", "all", "also", "am", "an", "and", "any", "are", "as", "at",
    "be", "because", "been", "before", "but", "by", "can", "could", "did", "do", "does",
    "for", "from", "had", "has", "have", "he", "her", "here", "him", "his", "how", "i",
    "if", "in", "into", "is", "it", "its", "just", "me", "more", "my", "no", "not",
    "now", "of", "on", "one", "only", "or", "our", "out", "over", "she", "should",
    "so", "some", "such", "than", "that", "the", "their", "them", "then", "there",
    "these", "they", "this", "those", "to", "too", "up", "us", "very", "was", "we",
    "were", "what", "when", "where", "which", "who", "why", "will", "with", "would",
    "you", "your",
}
WORD_RE = re.compile(r"[A-Za-z']+")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n{2,}")


def build_stylometry_profile(source_posts: list[dict[str, Any]], top_char_ngrams: int) -> dict[str, Any]:
    source_text = "\n\n".join(str(post.get("text", "")) for post in source_posts)
    return {
        "source_text": source_text,
        "vector": stylometry_vector(source_text),
        "char_ngram_keys": top_char_ngram_keys(source_text, top_char_ngrams),
    }


def stylometry_similarity(source_profile: dict[str, Any], candidate_text: str) -> float:
    source_vector = dict(source_profile.get("vector") or {})
    char_keys = list(source_profile.get("char_ngram_keys") or [])
    if char_keys:
        source_vector.update(char_ngram_vector_from_keys(source_profile.get("source_text", ""), char_keys))
    candidate_vector = stylometry_vector(candidate_text)
    candidate_vector.update(char_ngram_vector_from_keys(candidate_text, char_keys))
    return cosine_similarity(source_vector, candidate_vector)


def stylometry_vector(text: str) -> dict[str, float]:
    tokens = [token.lower().strip("'") for token in WORD_RE.findall(text)]
    tokens = [token for token in tokens if token]
    token_count = max(1, len(tokens))
    sentences = [sentence.strip() for sentence in SENTENCE_RE.split(text) if sentence.strip()]
    sentence_lengths = [len(WORD_RE.findall(sentence)) for sentence in sentences]
    sentence_count = max(1, len(sentence_lengths))
    paragraphs = [paragraph for paragraph in re.split(r"\n{2,}", text) if paragraph.strip()]
    paragraph_count = max(1, len(paragraphs))
    chars = max(1, len(text))

    vector: dict[str, float] = {}
    avg_sentence = sum(sentence_lengths) / sentence_count if sentence_lengths else 0.0
    vector["shape:avg_sentence_words"] = avg_sentence / 40
    vector["shape:sentence_std"] = _std(sentence_lengths) / 30
    vector["shape:short_sentence_ratio"] = sum(1 for value in sentence_lengths if value <= 6) / sentence_count
    vector["shape:long_sentence_ratio"] = sum(1 for value in sentence_lengths if value >= 25) / sentence_count
    vector["shape:avg_word_length"] = (sum(len(token) for token in tokens) / token_count) / 10
    vector["shape:type_token_ratio"] = len(set(tokens)) / token_count
    vector["shape:sentences_per_paragraph"] = sentence_count / paragraph_count / 10
    vector["shape:uppercase_ratio"] = sum(1 for ch in text if ch.isupper()) / chars * 20

    punctuation = {
        "comma": ",",
        "semicolon": ";",
        "colon": ":",
        "question": "?",
        "exclamation": "!",
        "quote": '"',
        "apostrophe": "'",
        "parenthesis": "(",
        "dash": "-",
    }
    for name, mark in punctuation.items():
        vector[f"punct:{name}"] = text.count(mark) / token_count * 25

    token_counts = Counter(tokens)
    for word in FUNCTION_WORDS:
        vector[f"fw:{word}"] = token_counts[word] / token_count * 20

    endings = Counter(token[-3:] for token in tokens if len(token) >= 5)
    for suffix, count in endings.most_common(40):
        vector[f"suffix:{suffix}"] = count / token_count * 10

    return vector


def top_char_ngram_keys(text: str, limit: int) -> list[str]:
    if limit <= 0:
        return []
    normalized = normalize_for_ngrams(text)
    counts = Counter(
        normalized[index:index + 3]
        for index in range(max(0, len(normalized) - 2))
        if normalized[index:index + 3].strip()
    )
    return [ngram for ngram, _ in counts.most_common(limit)]


def char_ngram_vector_from_keys(text: str, keys: list[str]) -> dict[str, float]:
    if not keys:
        return {}
    normalized = normalize_for_ngrams(text)
    total = max(1, len(normalized) - 2)
    counts = Counter(normalized[index:index + 3] for index in range(max(0, len(normalized) - 2)))
    return {f"char3:{key}": counts[key] / total * 50 for key in keys}


def normalize_for_ngrams(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def blend_scores(heuristic_score: float, stylometry_score: float, config: BenchmarkConfig) -> float:
    if config.scoring_mode == "heuristic":
        return heuristic_score
    if config.scoring_mode == "stylometry":
        return stylometry_score
    weight = max(0.0, min(1.0, config.stylometry_weight))
    return (heuristic_score * (1 - weight)) + (stylometry_score * weight)


def cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    keys = set(left) | set(right)
    if not keys:
        return 0.0
    dot = sum(float(left.get(key, 0.0)) * float(right.get(key, 0.0)) for key in keys)
    left_norm = math.sqrt(sum(float(left.get(key, 0.0)) ** 2 for key in keys))
    right_norm = math.sqrt(sum(float(right.get(key, 0.0)) ** 2 for key in keys))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (left_norm * right_norm)))


async def evaluate_post(
    service: BrandVoiceService,
    profile_path: Path,
    profile: dict[str, Any],
    stylometry_profile: dict[str, Any],
    post: dict[str, Any],
    label: int,
    anchor_author: str,
    config: BenchmarkConfig,
) -> dict[str, Any]:
    profile_json = json.dumps(profile, ensure_ascii=False, indent=2)
    profile_path.write_text(profile_json, encoding="utf-8")
    active_profile_path = Path(service._settings.BRAND_VOICE_PROFILE_PATH)
    active_profile_path.parent.mkdir(parents=True, exist_ok=True)
    active_profile_path.write_text(profile_json, encoding="utf-8")
    response = await service.evaluate(
        BrandVoiceEvaluateRequest(
            channel="blog",
            content_type="blog_post",
            content=post["text"],
            use_llm_judge=config.use_llm_judge,
        )
    )
    scores = response.dimension_scores
    heuristic_score = float(scores.get("writing_fingerprint_fit", response.overall_score))
    stylometry_score = round(stylometry_similarity(stylometry_profile, post["text"]) * 100, 2)
    final_score = round(blend_scores(heuristic_score, stylometry_score, config), 2)
    return {
        "anchor_author_id": anchor_author,
        "candidate_author_id": post["author_id"],
        "candidate_post_id": post["post_id"],
        "label": label,
        "score": final_score,
        "heuristic_score": heuristic_score,
        "stylometric_similarity": stylometry_score,
        "overall_score": response.overall_score,
        "tone_alignment": scores.get("tone_alignment"),
        "vocabulary": scores.get("vocabulary"),
        "readability": scores.get("readability"),
        "structure": scores.get("structure"),
        "identity_alignment": scores.get("identity_alignment"),
        "persona_fit": scores.get("persona_fit"),
        "writing_fingerprint_fit": scores.get("writing_fingerprint_fit"),
        "evaluation_method": response.evaluation_method,
    }


async def run_benchmark(
    processed_posts_path: Path,
    output_dir: Path,
    config: BenchmarkConfig,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    profiles_dir = output_dir / "profiles"
    profiles_dir.mkdir(exist_ok=True)
    authors = load_posts(processed_posts_path)
    selected = choose_authors(authors, config)
    rng = random.Random(config.seed)

    settings = Settings(
        BRAND_VOICE_PROFILE_PATH=str(output_dir / "active_profile.json"),
        BRAND_VOICE_DATASET_DIR=str(output_dir / "datasets"),
        DEBUG=False,
    )
    service = BrandVoiceService(NullVectorStore(), settings)

    pair_rows = []
    author_rows = []

    for author_id in selected:
        source_posts, positive_posts = split_author_posts(authors[author_id], config, rng)
        negative_posts = choose_negative_posts(author_id, selected, authors, config, rng)
        profile = build_profile(service, author_id, source_posts)
        stylometry_profile = build_stylometry_profile(source_posts, config.top_char_ngrams)
        profile_path = profiles_dir / f"{author_id}.json"

        positive_rows = [
            await evaluate_post(service, profile_path, profile, stylometry_profile, post, 1, author_id, config)
            for post in positive_posts
        ]
        negative_rows = [
            await evaluate_post(service, profile_path, profile, stylometry_profile, post, 0, author_id, config)
            for post in negative_posts
        ]
        pair_rows.extend(positive_rows)
        pair_rows.extend(negative_rows)
        author_rows.append(author_summary(author_id, source_posts, positive_rows, negative_rows))

    threshold = config.threshold if config.threshold is not None else best_threshold(pair_rows)
    summary = benchmark_summary(pair_rows, author_rows, selected, config, threshold)
    write_outputs(output_dir, config, summary, author_rows, pair_rows)
    return summary


def author_summary(
    author_id: str,
    source_posts: list[dict[str, Any]],
    positive_rows: list[dict[str, Any]],
    negative_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    same = [row["score"] for row in positive_rows]
    different = [row["score"] for row in negative_rows]
    return {
        "author_id": author_id,
        "source_posts": len(source_posts),
        "positive_pairs": len(positive_rows),
        "negative_pairs": len(negative_rows),
        "same_author_avg": round(_mean(same), 2),
        "different_author_avg": round(_mean(different), 2),
        "separation_gap": round(_mean(same) - _mean(different), 2),
    }


def benchmark_summary(
    pair_rows: list[dict[str, Any]],
    author_rows: list[dict[str, Any]],
    selected_authors: list[str],
    config: BenchmarkConfig,
    threshold: float,
) -> dict[str, Any]:
    positive = [row["score"] for row in pair_rows if row["label"] == 1]
    negative = [row["score"] for row in pair_rows if row["label"] == 0]
    positive_heuristic = [row["heuristic_score"] for row in pair_rows if row["label"] == 1]
    negative_heuristic = [row["heuristic_score"] for row in pair_rows if row["label"] == 0]
    positive_stylometry = [row["stylometric_similarity"] for row in pair_rows if row["label"] == 1]
    negative_stylometry = [row["stylometric_similarity"] for row in pair_rows if row["label"] == 0]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": config.to_json(),
        "authors_evaluated": len(selected_authors),
        "positive_pairs": len(positive),
        "negative_pairs": len(negative),
        "same_author_avg": round(_mean(positive), 2),
        "different_author_avg": round(_mean(negative), 2),
        "separation_gap": round(_mean(positive) - _mean(negative), 2),
        "heuristic_same_author_avg": round(_mean(positive_heuristic), 2),
        "heuristic_different_author_avg": round(_mean(negative_heuristic), 2),
        "stylometry_same_author_avg": round(_mean(positive_stylometry), 2),
        "stylometry_different_author_avg": round(_mean(negative_stylometry), 2),
        "roc_auc": round(roc_auc(pair_rows), 4),
        "best_threshold": threshold,
        "accuracy_at_threshold": round(accuracy_at_threshold(pair_rows, threshold), 4),
        "author_gap_avg": round(_mean([row["separation_gap"] for row in author_rows]), 2),
    }


def write_outputs(
    output_dir: Path,
    config: BenchmarkConfig,
    summary: dict[str, Any],
    author_rows: list[dict[str, Any]],
    pair_rows: list[dict[str, Any]],
) -> None:
    (output_dir / "config.json").write_text(json.dumps(config.to_json(), indent=2), encoding="utf-8")
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_csv(output_dir / "author_results.csv", author_rows)
    write_csv(output_dir / "pair_results.csv", pair_rows)
    write_jsonl(output_dir / "false_positives.jsonl", false_positives(pair_rows, summary["best_threshold"]))
    write_jsonl(output_dir / "false_negatives.jsonl", false_negatives(pair_rows, summary["best_threshold"]))
    write_report(output_dir / "report.md", summary)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_report(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Writing Fingerprint Benchmark Report",
        "",
        f"- Authors evaluated: {summary['authors_evaluated']}",
        f"- Positive pairs: {summary['positive_pairs']}",
        f"- Negative pairs: {summary['negative_pairs']}",
        f"- Same-author average: {summary['same_author_avg']}",
        f"- Different-author average: {summary['different_author_avg']}",
        f"- Separation gap: {summary['separation_gap']}",
        f"- Heuristic same/different average: {summary['heuristic_same_author_avg']} / {summary['heuristic_different_author_avg']}",
        f"- Stylometry same/different average: {summary['stylometry_same_author_avg']} / {summary['stylometry_different_author_avg']}",
        f"- ROC-AUC: {summary['roc_auc']}",
        f"- Best threshold: {summary['best_threshold']}",
        f"- Accuracy at threshold: {summary['accuracy_at_threshold']}",
        "",
        "Higher separation gap means the evaluator is better at distinguishing same-author style from other authors.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def best_threshold(pair_rows: list[dict[str, Any]]) -> float:
    if not pair_rows:
        return 75.0
    scores = sorted({float(row["score"]) for row in pair_rows})
    if not scores:
        return 75.0
    candidates = [(scores[i] + scores[i + 1]) / 2 for i in range(len(scores) - 1)]
    candidates.extend([scores[0] - 0.01, scores[-1] + 0.01])
    return round(max(candidates, key=lambda threshold: accuracy_at_threshold(pair_rows, threshold)), 2)


def accuracy_at_threshold(pair_rows: list[dict[str, Any]], threshold: float) -> float:
    if not pair_rows:
        return 0.0
    correct = 0
    for row in pair_rows:
        predicted = 1 if float(row["score"]) >= threshold else 0
        if predicted == int(row["label"]):
            correct += 1
    return correct / len(pair_rows)


def roc_auc(pair_rows: list[dict[str, Any]]) -> float:
    positives = [float(row["score"]) for row in pair_rows if int(row["label"]) == 1]
    negatives = [float(row["score"]) for row in pair_rows if int(row["label"]) == 0]
    if not positives or not negatives:
        return 0.0
    wins = 0.0
    total = len(positives) * len(negatives)
    for pos in positives:
        for neg in negatives:
            if pos > neg:
                wins += 1
            elif pos == neg:
                wins += 0.5
    return wins / total


def false_positives(pair_rows: list[dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
    return [row for row in pair_rows if row["label"] == 0 and float(row["score"]) >= threshold]


def false_negatives(pair_rows: list[dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
    return [row for row in pair_rows if row["label"] == 1 and float(row["score"]) < threshold]


def _mean(values: list[float]) -> float:
    return statistics.mean(values) if values else 0.0


def _std(values: list[int]) -> float:
    return statistics.pstdev(values) if len(values) > 1 else 0.0


def _close_age(a: Any, b: Any) -> bool:
    try:
        return abs(int(a) - int(b)) <= 5
    except (TypeError, ValueError):
        return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--posts", required=True, type=Path, help="Path to processed_posts.jsonl.")
    parser.add_argument("--output-dir", default=None, type=Path)
    parser.add_argument("--config", default=None, type=Path, help="Optional benchmark config JSON.")
    parser.add_argument("--max-authors", default=None, type=int)
    parser.add_argument("--negative-sampling", choices=["easy", "hard"], default=None)
    parser.add_argument("--scoring-mode", choices=["heuristic", "stylometry", "hybrid"], default=None)
    parser.add_argument("--stylometry-weight", default=None, type=float)
    parser.add_argument("--top-char-ngrams", default=None, type=int)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = BenchmarkConfig.from_json(args.config)
    if args.max_authors is not None:
        config = BenchmarkConfig(**{**config.to_json(), "max_authors": args.max_authors})
    if args.negative_sampling is not None:
        config = BenchmarkConfig(**{**config.to_json(), "negative_sampling": args.negative_sampling})
    if args.scoring_mode is not None:
        config = BenchmarkConfig(**{**config.to_json(), "scoring_mode": args.scoring_mode})
    if args.stylometry_weight is not None:
        config = BenchmarkConfig(**{**config.to_json(), "stylometry_weight": args.stylometry_weight})
    if args.top_char_ngrams is not None:
        config = BenchmarkConfig(**{**config.to_json(), "top_char_ngrams": args.top_char_ngrams})

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or Path("data/eval/blog_authorship/benchmark_runs") / run_id
    summary = asyncio.run(run_benchmark(args.posts, output_dir, config))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
