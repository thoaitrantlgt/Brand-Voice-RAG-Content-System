from scripts.run_seo_benchmark import DEFAULT_DATASET, load_cases, run_benchmark


def test_fixed_seo_benchmark_has_25_cases_and_honest_calibration_status():
    report = run_benchmark(load_cases(DEFAULT_DATASET))

    assert report["case_count"] == 25
    assert report["calibration_status"] == "pending_two_human_reviews"
    assert report["metric_schema_version"] == "content_seo_v2"
    assert report["spearman_human_score"] is None
    assert report["mean_absolute_error"] is None
    assert report["keyword_stuffing_recall"] == 1.0
    assert report["keyword_stuffing_false_positive_rate"] == 0.0
    assert report["severe_title_meta_recall"] >= 0.9
    assert report["fabricated_annotation_count"] == 0
    rows = {row["case_id"]: row for row in report["rows"]}
    for case_id in ("seo-24-natural-variation", "seo-25-semantic-good-no-exact"):
        assert not ({"keyword_usage", "title_issue"} & set(rows[case_id]["predicted_labels"]))


def test_partial_human_reviews_do_not_publish_calibration_statistics():
    cases = load_cases(DEFAULT_DATASET)
    for case in cases[:3]:
        case["human_reviews"] = [
            {"reviewer_id": "reviewer-a", "score": 70},
            {"reviewer_id": "reviewer-b", "score": 80},
        ]

    report = run_benchmark(cases)

    assert report["human_reviewed_case_count"] == 3
    assert report["calibration_status"] == "pending_two_human_reviews"
    assert report["spearman_human_score"] is None
    assert report["mean_absolute_error"] is None


def test_duplicate_reviewer_ids_do_not_count_as_independent_reviews():
    cases = load_cases(DEFAULT_DATASET)
    cases[0]["human_reviews"] = [
        {"reviewer_id": "same-reviewer", "score": 70},
        {"reviewer_id": "same-reviewer", "score": 80},
    ]

    report = run_benchmark(cases)

    assert report["human_reviewed_case_count"] == 0
