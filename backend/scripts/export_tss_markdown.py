"""Export the prepared TSS dataset as split-safe Markdown files."""
from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from pathlib import Path
from typing import Any


FOOTER_MARKERS = (
    "xem thêm các bài viết khác",
    "bài viết liên quan",
    "share:",
    "tin tức mới",
    "kênh truyền thông",
    "the sun symphony. all rights reserved.",
    "proudly powered by",
)


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.replace("Đ", "D").replace("đ", "d"))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-") or "article"


def clean_title(title: str) -> str:
    return re.sub(
        r"\s+Footer Demo\s+[\u2013-]\s+The Sun Symphony\s*$",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()


def clean_article_body(title: str, article: str) -> str:
    title = clean_title(title)
    normalized = unicodedata.normalize("NFC", article).replace("\r\n", "\n").replace("\r", "\n")

    title_start = normalized.lower().rfind(title.lower())
    if title_start >= 0:
        normalized = normalized[title_start + len(title) :]

    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in normalized.splitlines()]
    while lines and (not lines[0] or lines[0].casefold() == title.casefold()):
        lines.pop(0)

    content_lines: list[str] = []
    for line in lines:
        lowered = line.casefold().rstrip(":")
        if any(lowered.startswith(marker.rstrip(":")) for marker in FOOTER_MARKERS):
            break
        if line or (content_lines and content_lines[-1]):
            content_lines.append(line)

    while content_lines and not content_lines[-1]:
        content_lines.pop()
    return "\n".join(content_lines).strip()


def classify_sample(dataset_split: str, rating: int) -> str:
    if dataset_split == "test":
        return "holdout"
    if rating >= 4:
        return "writing_samples"
    return "negative_samples"


def _yaml_string(value: object) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def render_markdown(title: str, body: str, metadata: dict[str, Any]) -> str:
    frontmatter = ["---"]
    for key in ("source_url", "category"):
        frontmatter.append(f"{key}: {_yaml_string(metadata[key])}")
    frontmatter.extend(
        [
            f"rating: {int(metadata['rating'])}",
            f"dataset_split: {metadata['dataset_split']}",
            "---",
        ]
    )
    return "\n".join([*frontmatter, "", f"# {title}", "", body.strip(), ""])


def export_dataset(dataset_dir: Path, output_dir: Path) -> dict[str, int]:
    articles = json.loads((dataset_dir / "article_texts.json").read_text(encoding="utf-8"))
    split_manifest = json.loads((dataset_dir / "split_manifest.json").read_text(encoding="utf-8"))

    split_by_url = {
        record["link"]: dataset_split
        for dataset_split, records in split_manifest.items()
        for record in records
    }
    records = [record for records in split_manifest.values() for record in records]
    target_names = ("writing_samples", "negative_samples", "holdout")
    for target_name in target_names:
        target_dir = output_dir / target_name
        target_dir.mkdir(parents=True, exist_ok=True)
        for old_file in target_dir.glob("*.md"):
            old_file.unlink()

    manifest_rows: list[dict[str, Any]] = []
    counts = {target_name: 0 for target_name in target_names}
    for record in sorted(records, key=lambda item: int(item["stt"])):
        source = articles.get(record["link"])
        if not source:
            raise ValueError(f"Missing article text for STT {record['stt']}: {record['link']}")

        title = clean_title(source.get("title") or f"TSS article {record['stt']}")
        body = clean_article_body(title, source.get("text") or "")
        if not body:
            raise ValueError(f"Article STT {record['stt']} is empty after cleaning")

        dataset_split = split_by_url[record["link"]]
        target_name = classify_sample(dataset_split, int(record["rating"]))
        filename = f"{int(record['stt']):02d}-{slugify(title)[:90]}.md"
        relative_path = Path(target_name) / filename
        metadata = {
            "source_url": record["link"],
            "category": record["category"],
            "rating": int(record["rating"]),
            "dataset_split": dataset_split,
        }
        (output_dir / relative_path).write_text(
            render_markdown(title, body, metadata), encoding="utf-8"
        )
        counts[target_name] += 1
        manifest_rows.append(
            {
                "stt": int(record["stt"]),
                "title": title,
                **metadata,
                "avoid": record.get("avoid", ""),
                "prefer": record.get("prefer", ""),
                "markdown_path": relative_path.as_posix(),
                "character_count": len(body),
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest_rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (output_dir / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest_rows[0]))
        writer.writeheader()
        writer.writerows(manifest_rows)
    (output_dir / "README.md").write_text(
        "# TSS Markdown Export\n\n"
        "- `writing_samples/`: train articles rated 4-5; upload these as writing samples.\n"
        "- `negative_samples/`: train articles rated 1-3; do not train the voice profile on these.\n"
        "- `holdout/`: test articles; keep these isolated for evaluation.\n"
        "- `manifest.csv` and `manifest.json`: source metadata and human annotations.\n",
        encoding="utf-8",
    )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-dir", type=Path, default=Path("data/eval/tss_pipeline_v2")
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/exports/tss_markdown")
    )
    args = parser.parse_args()
    counts = export_dataset(args.dataset_dir, args.output_dir)
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == "__main__":
    main()
