from app.services.seo_evaluation_service import SeoEvaluationService


BRIEF = {
    "topic": "Cách kiểm soát hơi khi hát cho người mới",
    "keywords": ["kiểm soát hơi"],
    "primary_keyword": "kiểm soát hơi",
    "search_intent": "informational",
    "objective": "Hướng dẫn người mới luyện kiểm soát luồng hơi an toàn",
    "must_cover": ["dấu hiệu hụt hơi", "bài tập kiểm soát luồng hơi"],
}


def test_complete_article_has_explainable_seo_readiness_report():
    content = """# Cách kiểm soát hơi khi hát cho người mới

Kiểm soát hơi giúp người mới giữ câu hát ổn định. Bài viết này chỉ ra dấu hiệu hụt hơi và cách luyện từng bước an toàn.

## Dấu hiệu bạn đang hụt hơi

Bạn thường hết hơi giữa câu, vai nhấc lên khi hít vào hoặc âm thanh mất ổn định ở cuối câu.

## Bài tập kiểm soát luồng hơi

Hít vào nhẹ nhàng, sau đó phát âm xì đều trong 10 giây. Ghi lại thời gian và dừng nếu thấy căng cổ.

## Cách theo dõi tiến bộ

Luyện ngắn mỗi ngày và so sánh độ ổn định thay vì cố kéo dài bằng mọi giá.
"""
    result = SeoEvaluationService().evaluate(
        content=content,
        brief=BRIEF,
        seo_title="Cách kiểm soát hơi khi hát cho người mới",
        meta_description="Nhận biết dấu hiệu hụt hơi và luyện kiểm soát luồng hơi từng bước an toàn cho người mới học hát.",
    )

    assert result["score"] >= 75
    assert result["gated"] is False
    assert result["included_in_overall"] is False
    assert set(result["subscores"]) == {
        "search_intent_satisfaction",
        "helpful_completeness",
        "information_gain_originality",
        "evidence_expertise_trust",
        "title_snippet_accuracy",
        "semantic_topic_coverage",
        "structure_scannability",
    }
    assert all({"code", "status", "severity", "evidence", "recommendation"} <= set(item) for item in result["checks"])


def test_generic_metadata_and_weak_structure_are_reported_separately():
    result = SeoEvaluationService().evaluate(
        content="# Một tiêu đề khác\n\nNội dung ngắn và chưa trả lời nhu cầu.",
        brief=BRIEF,
        seo_title="Tin mới hôm nay",
        meta_description="Blog post about singing",
    )

    assert result["score"] < 75
    fields = {item["field"] for item in result["field_issues"]}
    assert fields == {"seo_title", "meta_description"}
    assert result["subscores"]["structure_scannability"] < 75
    assert result["score"] <= 74
    assert result["weighted_score"] >= result["score"]


def test_keyword_repetition_is_a_heuristic_not_a_density_target():
    repeated = "Kiểm soát hơi kiểm soát hơi giúp bạn kiểm soát hơi. " * 12
    result = SeoEvaluationService().evaluate(
        content=f"# Kiểm soát hơi\n\n{repeated}\n\n## Bài tập\n\n{repeated}\n\n## Lưu ý\n\nDừng khi khó chịu.",
        brief=BRIEF,
        seo_title="Kiểm soát hơi cho người mới",
        meta_description="Hướng dẫn kiểm soát hơi với bài tập thực hành và lưu ý an toàn cho người mới học hát.",
    )

    assert any(item["code"] == "keyword_repetition" for item in result["checks"])
    assert result["annotations"][0]["metric"] == "seo"
    assert result["score"] <= 64


def test_auto_intent_is_inferred_from_how_to_topic():
    result = SeoEvaluationService().evaluate(
        content="# Cách luyện hát\n\nCách luyện hát cho người mới.\n\n## Bước một\n\nThực hành.\n\n## Bước hai\n\nTheo dõi.",
        brief={**BRIEF, "search_intent": "auto"},
        seo_title="Cách luyện hát cho người mới",
        meta_description="Các bước luyện hát cơ bản giúp người mới bắt đầu thực hành có mục tiêu và theo dõi tiến bộ.",
    )

    assert result["search_intent"] == "informational"


def test_optional_seo_gate_contract_is_exposed_when_enabled():
    result = SeoEvaluationService(gate_enabled=True, threshold=82).evaluate(
        content="# Topic\n\nShort body.\n\n## One\n\nText.\n\n## Two\n\nText.",
        brief=BRIEF,
        seo_title="Topic",
        meta_description="Short description",
    )

    assert result["gated"] is True
    assert result["threshold"] == 82


def test_duplicate_title_and_meta_are_checked_within_project_input():
    title = "Cách kiểm soát hơi khi hát cho người mới"
    meta = "Nhận biết dấu hiệu hụt hơi và luyện kiểm soát luồng hơi từng bước an toàn."
    result = SeoEvaluationService().evaluate(
        content=f"# {title}\n\n{meta}\n\n## Dấu hiệu\n\nHụt hơi.\n\n## Bài tập\n\nLuyện tập.",
        brief=BRIEF,
        seo_title=title,
        meta_description=meta,
        suggested_slug="cach-kiem-soat-hoi",
        existing_project_blogs=[{"seo_title": title, "meta_description": meta}],
    )

    codes = {item["code"] for item in result["checks"]}
    assert {"duplicate_seo_title", "duplicate_meta_description"} <= codes
    assert result["seo_package"]["suggested_slug"] == "cach-kiem-soat-hoi"


def test_optional_llm_blends_judgment_dimensions_but_keeps_mechanical_scores():
    class Judge:
        def call(self, messages):
            assert messages[0]["role"] == "system"
            assert "untrusted" in messages[0]["content"]
            return '{"search_intent_satisfaction": 20, "helpful_completeness": 30, "information_gain_originality": 30, "evidence_expertise_trust": 40, "semantic_topic_coverage": 50, "reason": "Bài còn nông."}'

    deterministic = SeoEvaluationService().evaluate(
        content="# Kiểm soát hơi\n\nHướng dẫn kiểm soát hơi.\n\n## Dấu hiệu\n\nHụt hơi.\n\n## Bài tập\n\nThực hành.",
        brief=BRIEF,
        seo_title="Kiểm soát hơi cho người mới",
        meta_description="Hướng dẫn kiểm soát hơi cho người mới với dấu hiệu và bài tập thực hành.",
    )
    judged = SeoEvaluationService(llm=Judge(), llm_enabled=True).evaluate(
        content="# Kiểm soát hơi\n\nHướng dẫn kiểm soát hơi.\n\n## Dấu hiệu\n\nHụt hơi.\n\n## Bài tập\n\nThực hành.",
        brief=BRIEF,
        seo_title="Kiểm soát hơi cho người mới",
        meta_description="Hướng dẫn kiểm soát hơi cho người mới với dấu hiệu và bài tập thực hành.",
    )

    assert judged["judge_status"] == "evaluated"
    assert judged["subscores"]["search_intent_satisfaction"] == round(
        (deterministic["subscores"]["search_intent_satisfaction"] + 20) / 2
    )
    assert judged["subscores"]["information_gain_originality"] == round(
        (deterministic["subscores"]["information_gain_originality"] + 30) / 2
    )
    assert judged["subscores"]["title_snippet_accuracy"] == deterministic["subscores"]["title_snippet_accuracy"]


def test_incomplete_llm_judge_output_falls_back_to_deterministic_scores():
    class IncompleteJudge:
        def call(self, messages):
            return '{"search_intent_satisfaction": 10, "helpful_completeness": 20}'

    kwargs = {
        "content": "# Kiểm soát hơi\n\nHướng dẫn kiểm soát hơi.\n\n## Dấu hiệu\n\nHụt hơi.\n\n## Bài tập\n\nThực hành.",
        "brief": BRIEF,
        "seo_title": "Kiểm soát hơi cho người mới",
        "meta_description": "Hướng dẫn kiểm soát hơi cho người mới với dấu hiệu và bài tập thực hành.",
    }
    deterministic = SeoEvaluationService().evaluate(**kwargs)
    judged = SeoEvaluationService(llm=IncompleteJudge(), llm_enabled=True).evaluate(**kwargs)

    assert judged["judge_status"] == "error"
    assert judged["subscores"] == deterministic["subscores"]


def test_correct_h1_cannot_hide_an_unrelated_article_body():
    result = SeoEvaluationService().evaluate(
        content="""# Cách giữ hơi khi hát cho người mới

Lập ngân sách gia đình bắt đầu bằng việc ghi lại tiền thuê nhà và hóa đơn điện.

## Chia nhóm chi tiêu

Tôi dùng bảng tính để so sánh 30 khoản mua sắm mỗi tháng.

## Theo dõi tiết kiệm

Xem [hướng dẫn ngân sách](https://example.org/budget) và đặt giới hạn an toàn cho thẻ.
""",
        brief=BRIEF,
        seo_title="Cách giữ hơi khi hát cho người mới",
        meta_description="Hướng dẫn giữ hơi khi hát và luyện kiểm soát luồng khí cho người mới.",
    )

    assert result["subscores"]["search_intent_satisfaction"] < 50
    assert result["subscores"]["helpful_completeness"] < 50
    assert result["score"] < 75


def test_semantically_equivalent_title_and_h1_do_not_trigger_mismatch_cap():
    result = SeoEvaluationService(
        semantic_similarity=lambda expected, actual: 0.9
    ).evaluate(
        content="""# Phân phối luồng khí để hát trọn câu

Người mới thường hết hơi khi xả khí quá nhanh ở đầu câu.

## Nguyên nhân

Vai nhấc và luồng khí thoát mạnh làm câu hát thiếu ổn định.

## Bài tập

Đọc chậm, đánh dấu chỗ lấy hơi và dừng nếu thấy căng cổ.
""",
        brief=BRIEF,
        seo_title="Cách giữ hơi khi hát cho người mới",
        meta_description="Nhận biết nguyên nhân hụt hơi và luyện phân phối luồng khí để hát trọn câu an toàn.",
    )

    assert not any(item["code"] == "title_content_mismatch" for item in result["checks"])
    assert result["weighted_score"] == result["score"]


def test_semantic_similarity_accepts_natural_keyword_variation_without_exact_match():
    content = """# Khắc phục hết hơi giữa câu hát

Hết hơi giữa câu thường liên quan đến cách lấy và phân phối luồng khí.

## Nguyên nhân thường gặp

Bạn có thể hít quá nhiều hoặc xả khí quá nhanh ở đầu câu.

## Bài tập phân phối khí

Đọc lời theo nhịp, đánh dấu chỗ lấy hơi và hát từng câu ngắn.
"""
    result = SeoEvaluationService(
        semantic_similarity=lambda expected, actual: 0.86
    ).evaluate(
        content=content,
        brief={
            **BRIEF,
            "topic": "Khắc phục tình trạng hết hơi giữa câu hát",
            "objective": "Giúp người mới hoàn thành câu hát",
        },
        seo_title="Khắc phục hết hơi giữa câu hát",
        meta_description="Nhận biết nguyên nhân hết hơi và luyện phân phối luồng khí để hoàn thành câu hát ổn định hơn.",
    )

    assert result["subscores"]["semantic_topic_coverage"] >= 80
    assert not any(item["code"] == "keyword_usage" and item["status"] == "needs_attention" for item in result["checks"])
    assert not any(item["field"] == "seo_title" for item in result["field_issues"])


def test_specific_experience_and_evidence_outscore_generic_filler():
    generic = SeoEvaluationService().evaluate(
        content="# Luyện hát\n\nLuyện hát rất quan trọng.\n\n## Cách tập\n\nHãy tập thường xuyên.\n\n## Kết luận\n\nKiên trì để tiến bộ.",
        brief={**BRIEF, "topic": "Luyện hát", "keywords": ["luyện hát"]},
        seo_title="Luyện hát",
        meta_description="Một số gợi ý luyện hát cho người mới.",
    )
    specific = SeoEvaluationService().evaluate(
        content="# Luyện hát\n\nTrong buổi tập đầu tiên, hãy thu âm một câu 15 giây để có mốc so sánh.\n\n## Ví dụ thực hành\n\nTôi thường đánh dấu chỗ lấy hơi bằng dấu gạch chéo, sau đó luyện ba lần ở tốc độ chậm.\n\n## Giới hạn an toàn\n\nDừng bài tập nếu cổ đau; hướng dẫn này không thay thế đánh giá của chuyên gia y tế. Xem [hướng dẫn chính thức](https://example.org/guide).",
        brief={**BRIEF, "topic": "Luyện hát", "keywords": ["luyện hát"]},
        seo_title="Luyện hát",
        meta_description="Một quy trình luyện hát có mốc thu âm, ví dụ thực hành và giới hạn an toàn cho người mới.",
    )

    assert specific["subscores"]["information_gain_originality"] > generic["subscores"]["information_gain_originality"]
    assert specific["subscores"]["evidence_expertise_trust"] > generic["subscores"]["evidence_expertise_trust"]
