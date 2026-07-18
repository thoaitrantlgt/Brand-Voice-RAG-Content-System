"""Prepare Blog Authorship Corpus files for offline writing-fingerprint evaluation.

Input can be the raw ``blogs.zip`` file or an extracted directory containing
``*.xml`` files. Output is JSONL with one cleaned post per line plus an author
index summary.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@dataclass(frozen=True)
class BlogPost:
    post_id: str
    author_id: str
    gender: str
    age: int | None
    job: str
    horoscope: str
    date: str
    text: str
    word_count: int

    def to_json(self) -> dict:
        return {
            "post_id": self.post_id,
            "author_id": self.author_id,
            "gender": self.gender,
            "age": self.age,
            "job": self.job,
            "horoscope": self.horoscope,
            "date": self.date,
            "text": self.text,
            "word_count": self.word_count,
        }


FILENAME_RE = re.compile(
    r"(?P<author_id>[^.\\/]+)\."
    r"(?P<gender>[^.\\/]+)\."
    r"(?P<age>\d+)\."
    r"(?P<job>[^.\\/]+)\."
    r"(?P<horoscope>[^.\\/]+)\.xml$",
    re.IGNORECASE,
)
POST_RE = re.compile(
    r"<date>\s*(?P<date>.*?)\s*</date>\s*<post>\s*(?P<post>.*?)\s*</post>",
    re.IGNORECASE | re.DOTALL,
)
TAG_RE = re.compile(r"<[^>]+>")


def parse_metadata(path_name: str) -> dict | None:
    match = FILENAME_RE.search(path_name.replace("\\", "/"))
    if not match:
        return None
    raw = match.groupdict()
    return {
        "author_id": raw["author_id"],
        "gender": raw["gender"],
        "age": int(raw["age"]) if raw["age"].isdigit() else None,
        "job": raw["job"],
        "horoscope": raw["horoscope"],
    }


def clean_post_text(raw: str) -> str:
    text = html.unescape(raw)
    text = TAG_RE.sub(" ", text)
    text = text.replace("\x00", " ")
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text, flags=re.UNICODE))


def parse_blog_file(path_name: str, payload: str) -> list[BlogPost]:
    metadata = parse_metadata(path_name)
    if not metadata:
        return []

    payload = payload.replace("<![CDATA[", "").replace("]]>", "")
    posts = []
    for index, match in enumerate(POST_RE.finditer(payload)):
        text = clean_post_text(match.group("post"))
        count = word_count(text)
        if not text:
            continue
        posts.append(
            BlogPost(
                post_id=f"{metadata['author_id']}:{index}",
                author_id=metadata["author_id"],
                gender=metadata["gender"],
                age=metadata["age"],
                job=metadata["job"],
                horoscope=metadata["horoscope"],
                date=clean_post_text(match.group("date")),
                text=text,
                word_count=count,
            )
        )
    return posts


def iter_raw_files(input_path: Path) -> Iterable[tuple[str, str]]:
    if input_path.is_file() and input_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(input_path) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".xml"):
                    with zf.open(name) as handle:
                        yield name, handle.read().decode("utf-8", errors="ignore")
        return

    if input_path.is_dir():
        for path in input_path.rglob("*.xml"):
            yield str(path), path.read_text(encoding="utf-8", errors="ignore")
        return

    raise ValueError(f"Input must be a blogs.zip file or directory: {input_path}")


def prepare_dataset(
    input_path: Path,
    output_dir: Path,
    min_words_per_post: int = 150,
    max_words_per_post: int = 2000,
    min_posts_per_author: int = 8,
    max_authors: int | None = None,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_posts_by_author: dict[str, list[BlogPost]] = defaultdict(list)
    skipped_short = 0
    skipped_long = 0

    for path_name, payload in iter_raw_files(input_path):
        for post in parse_blog_file(path_name, payload):
            if post.word_count < min_words_per_post:
                skipped_short += 1
                continue
            if post.word_count > max_words_per_post:
                skipped_long += 1
                continue
            raw_posts_by_author[post.author_id].append(post)

    eligible = [
        (author_id, posts)
        for author_id, posts in raw_posts_by_author.items()
        if len(posts) >= min_posts_per_author
    ]
    eligible.sort(key=lambda item: len(item[1]), reverse=True)
    if max_authors:
        eligible = eligible[:max_authors]

    processed_path = output_dir / "processed_posts.jsonl"
    author_index_path = output_dir / "author_index.json"
    author_index = {}
    total_posts = 0

    with processed_path.open("w", encoding="utf-8") as f:
        for author_id, posts in eligible:
            posts = sorted(posts, key=lambda post: (post.date, post.post_id))
            word_counts = [post.word_count for post in posts]
            first = posts[0]
            author_index[author_id] = {
                "author_id": author_id,
                "gender": first.gender,
                "age": first.age,
                "job": first.job,
                "horoscope": first.horoscope,
                "post_count": len(posts),
                "total_words": sum(word_counts),
                "avg_words": round(sum(word_counts) / max(1, len(word_counts)), 1),
            }
            for post in posts:
                f.write(json.dumps(post.to_json(), ensure_ascii=False) + "\n")
                total_posts += 1

    summary = {
        "input": str(input_path),
        "output_dir": str(output_dir),
        "processed_posts_path": str(processed_path),
        "author_index_path": str(author_index_path),
        "authors_total_raw": len(raw_posts_by_author),
        "authors_eligible": len(eligible),
        "posts_written": total_posts,
        "skipped_short": skipped_short,
        "skipped_long": skipped_long,
        "min_words_per_post": min_words_per_post,
        "max_words_per_post": max_words_per_post,
        "min_posts_per_author": min_posts_per_author,
        "gender_counts": Counter(item["gender"] for item in author_index.values()),
    }

    with author_index_path.open("w", encoding="utf-8") as f:
        json.dump({"authors": author_index, "summary": summary}, f, ensure_ascii=False, indent=2)

    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Path to blogs.zip or extracted raw XML directory.")
    parser.add_argument("--output-dir", default=Path("data/eval/blog_authorship"), type=Path)
    parser.add_argument("--min-words-per-post", default=150, type=int)
    parser.add_argument("--max-words-per-post", default=2000, type=int)
    parser.add_argument("--min-posts-per-author", default=8, type=int)
    parser.add_argument("--max-authors", default=None, type=int)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = prepare_dataset(
        input_path=args.input,
        output_dir=args.output_dir,
        min_words_per_post=args.min_words_per_post,
        max_words_per_post=args.max_words_per_post,
        min_posts_per_author=args.min_posts_per_author,
        max_authors=args.max_authors,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
