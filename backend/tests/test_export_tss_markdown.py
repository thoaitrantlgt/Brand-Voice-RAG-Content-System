from scripts.export_tss_markdown import (
    clean_article_body,
    classify_sample,
    render_markdown,
    slugify,
)


def test_clean_article_body_removes_navigation_duplicate_title_and_footer():
    title = "Cách giữ hơi khi hát"
    article = "\n".join(
        [
            "Back",
            "THE SUN SYMPHONY",
            title,
            "Nội dung bài viết đầu tiên.",
            "Nội dung bài viết thứ hai đủ dài để được giữ lại.",
            "Xem thêm các bài viết khác:",
            "Bài viết không liên quan",
            "Share:",
        ]
    )

    assert clean_article_body(title, article) == (
        "Nội dung bài viết đầu tiên.\n"
        "Nội dung bài viết thứ hai đủ dài để được giữ lại."
    )


def test_classify_sample_keeps_only_high_rated_train_items_as_writing_samples():
    assert classify_sample("train", 4) == "writing_samples"
    assert classify_sample("train", 5) == "writing_samples"
    assert classify_sample("train", 3) == "negative_samples"
    assert classify_sample("test", 5) == "holdout"


def test_render_markdown_has_frontmatter_and_one_h1():
    content = render_markdown(
        title="Kỹ thuật lấy hơi",
        body="Đoạn nội dung chính.",
        metadata={
            "source_url": "https://example.com/ky-thuat-lay-hoi/",
            "category": "Kỹ thuật",
            "rating": 5,
            "dataset_split": "train",
        },
    )

    assert content.count("# Kỹ thuật lấy hơi") == 1
    assert 'source_url: "https://example.com/ky-thuat-lay-hoi/"' in content
    assert 'category: "Kỹ thuật"' in content
    assert "rating: 5" in content
    assert "dataset_split: train" in content


def test_slugify_produces_stable_ascii_filename_component():
    assert slugify("Kỹ thuật lấy hơi đúng cách") == "ky-thuat-lay-hoi-dung-cach"
