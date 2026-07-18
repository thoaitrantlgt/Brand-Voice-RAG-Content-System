import json
import zipfile

import pytest

from scripts.prepare_blog_authorship_eval import parse_blog_file, prepare_dataset
from scripts.run_writing_fingerprint_benchmark import (
    BenchmarkConfig,
    accuracy_at_threshold,
    best_threshold,
    build_stylometry_profile,
    roc_auc,
    run_benchmark,
    stylometry_similarity,
)


def test_parse_blog_file_extracts_metadata_and_posts():
    payload = """
    <Blog>
      <date>01,August,2004</date>
      <post>Hello there. This is a clean test post.</post>
      <date>02,August,2004</date>
      <post><![CDATA[Another post &amp; more text.]]></post>
    </Blog>
    """

    posts = parse_blog_file("5114.male.25.indUnk.Sagittarius.xml", payload)

    assert len(posts) == 2
    assert posts[0].author_id == "5114"
    assert posts[0].gender == "male"
    assert posts[0].age == 25
    assert posts[0].post_id == "5114:0"
    assert "clean test post" in posts[0].text


def test_prepare_dataset_writes_processed_jsonl_and_author_index(tmp_path):
    xml = """
    <Blog>
      <date>01,August,2004</date>
      <post>One two three four five six seven eight nine ten.</post>
      <date>02,August,2004</date>
      <post>Alpha beta gamma delta epsilon zeta eta theta iota kappa.</post>
    </Blog>
    """
    zip_path = tmp_path / "blogs.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("5114.male.25.indUnk.Sagittarius.xml", xml)

    summary = prepare_dataset(
        input_path=zip_path,
        output_dir=tmp_path / "prepared",
        min_words_per_post=3,
        max_words_per_post=50,
        min_posts_per_author=2,
    )

    assert summary["authors_eligible"] == 1
    assert summary["posts_written"] == 2

    rows = [
        json.loads(line)
        for line in (tmp_path / "prepared" / "processed_posts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["author_id"] == "5114"
    assert (tmp_path / "prepared" / "author_index.json").exists()


def test_benchmark_metrics_separate_positive_and_negative_pairs():
    rows = [
        {"label": 1, "score": 90},
        {"label": 1, "score": 80},
        {"label": 0, "score": 40},
        {"label": 0, "score": 30},
    ]

    threshold = best_threshold(rows)

    assert roc_auc(rows) == 1.0
    assert accuracy_at_threshold(rows, threshold) == 1.0


def test_stylometry_similarity_prefers_matching_style():
    source_posts = [
        {
            "text": (
                "I keep this direct, practical, and short. Why does it matter? "
                "Because the point is implementation. Short note."
            )
        },
        {
            "text": (
                "I keep this direct, practical, and short. The point is simple. "
                "Why does it matter? Because the work needs implementation."
            )
        },
    ]
    profile = build_stylometry_profile(source_posts, top_char_ngrams=80)

    matching = stylometry_similarity(
        profile,
        "I keep this direct, practical, and short. Why does it matter? Because implementation is the point.",
    )
    different = stylometry_similarity(
        profile,
        "Yesterday felt like a soft memory beside the window, where every color became sentimental and slow.",
    )

    assert matching > different


@pytest.mark.asyncio
async def test_run_benchmark_writes_summary_and_pair_results(tmp_path):
    posts_path = tmp_path / "processed_posts.jsonl"
    rows = []
    for author_id, phrase in [("a1", "mentor direct practical"), ("a2", "diary emotional personal")]:
        for index in range(8):
            rows.append(
                {
                    "post_id": f"{author_id}:{index}",
                    "author_id": author_id,
                    "gender": "male",
                    "age": 30,
                    "job": "tech",
                    "horoscope": "Aries",
                    "date": f"2004-08-{index + 1:02d}",
                    "word_count": 30,
                    "text": f"{phrase}. This sentence keeps the author pattern. Short note. Why does this matter? {phrase}.",
                }
            )
    posts_path.write_text(
        "\n".join(json.dumps(row) for row in rows),
        encoding="utf-8",
    )

    summary = await run_benchmark(
        processed_posts_path=posts_path,
        output_dir=tmp_path / "run",
        config=BenchmarkConfig(
            seed=7,
            max_authors=2,
            source_posts_per_author=3,
            positive_posts_per_author=2,
            negative_posts_per_author=2,
            min_posts_per_author=8,
            negative_sampling="easy",
        ),
    )

    assert summary["authors_evaluated"] == 2
    assert summary["positive_pairs"] == 4
    assert summary["negative_pairs"] == 4
    assert "stylometry_same_author_avg" in summary
    assert "heuristic_same_author_avg" in summary
    assert (tmp_path / "run" / "summary.json").exists()
    assert (tmp_path / "run" / "pair_results.csv").exists()
