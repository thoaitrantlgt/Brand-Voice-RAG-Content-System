import json
from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.schemas.document import BrandVoiceEvaluateRequest, TrainBrandVoiceRequest
from app.services.brand_voice_service import BrandVoiceService, PROFILE_DOCUMENT_ID


@pytest.mark.asyncio
async def test_train_brand_voice_creates_profile_dataset_and_indexes(tmp_path):
    store = MagicMock()
    store.get_documents.return_value = [
        {
            "id": "doc-1-0",
            "text": "# Title One\n\nMo dau ro rang.\n\nNoi dung chinh ve AI va tu dong hoa.",
            "metadata": {
                "document_id": "doc-1",
                "filename": "one.md",
                "chunk_index": "0",
                "purpose": "brand_voice",
            },
        },
        {
            "id": "doc-2-0",
            "text": "# Title Two\n\nBai viet than thien va thuc te ve marketing.",
            "metadata": {
                "document_id": "doc-2",
                "filename": "two.md",
                "chunk_index": "0",
                "purpose": "both",
            },
        },
    ]
    store.delete_document.return_value = 0

    settings = Settings(
        BRAND_VOICE_PROFILE_PATH=str(tmp_path / "brand_voice_profile.json"),
        BRAND_VOICE_DATASET_DIR=str(tmp_path / "brand_voice"),
    )
    service = BrandVoiceService(store, settings)

    result = await service.train(
        TrainBrandVoiceRequest(company_name="Acme", min_documents=1, max_documents=30)
    )

    assert result.company_name == "Acme"
    assert result.source_document_count == 2
    assert result.indexed_chunks >= 1
    assert "Brand Voice Profile" in result.profile_markdown
    assert "Calibration Tests" in result.profile_markdown
    assert "Governance" in result.profile_markdown
    assert (tmp_path / "brand_voice_profile.json").exists()
    assert (tmp_path / "brand_voice" / "brand_voice_sft.jsonl").exists()
    assert (tmp_path / "brand_voice" / "brand_voice_dpo_seed.jsonl").exists()

    store.delete_document.assert_called_once_with(PROFILE_DOCUMENT_ID)
    store.add_documents.assert_called_once()
    _, metadatas, _ = store.add_documents.call_args.args
    assert metadatas[0]["content_type"] == "brand_voice_profile"

    first_row = json.loads((tmp_path / "brand_voice" / "brand_voice_sft.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert first_row["messages"][2]["role"] == "assistant"

    profile = json.loads((tmp_path / "brand_voice_profile.json").read_text(encoding="utf-8"))
    assert profile["training_method_recommendation"]["recommended_method"] == "prompt_engineering"
    assert len(profile["calibration_tests"]) == 10


@pytest.mark.asyncio
async def test_evaluate_brand_voice_returns_scores(tmp_path):
    profile_path = tmp_path / "brand_voice_profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "profile_id": "profile-1",
                "company_name": "Acme",
                "vocabulary": {
                    "preferred_phrases": ["AI", "marketing"],
                    "repeated_terms": ["automation"],
                    "forbidden_terms": ["magic"],
                },
                "dictionary": {"forbidden_replacements": {"hack": "workflow"}},
                "style_rules": {"max_sentence_words": 18},
                "channel_guidelines": {
                    "blog": {"rules": ["Use clear H2 sections.", "Avoid unsupported hype."]}
                },
                "governance": {"reviewer_checklist": ["Check tone.", "Check facts."]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    settings = Settings(BRAND_VOICE_PROFILE_PATH=str(profile_path))
    service = BrandVoiceService(MagicMock(), settings)

    result = await service.evaluate(
        BrandVoiceEvaluateRequest(
            channel="blog",
            content_type="blog_post",
            content="# Title\n\n## Section\n\nAI marketing automation avoids generic phrasing.",
        )
    )

    assert result.profile_id == "profile-1"
    assert result.overall_score > 70
    assert result.reviewer_checklist == ["Check tone.", "Check facts."]
