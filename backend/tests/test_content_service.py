from app.services.content_service import ContentService
from app.core.style_guide import StyleGuide
import pytest


class FakeCrew:
    def run(self, inputs):
        return {
            "raw_output": """
            {
              "titles": [
                {
                  "keyword": "AI blog",
                  "title": "Draft 1",
                  "seo_title": "Draft SEO",
                  "outline": ["Mo dau", "Noi dung chinh"]
                },
                {
                  "keyword": "AI blog",
                  "title": "Draft 2",
                  "seo_title": "Draft 2 SEO",
                  "outline": ["Ignored"]
                }
              ]
            }
            """,
            "status": "success",
        }


class FakeContentCrew:
    def __init__(self):
        self.last_inputs = None

    def run(self, inputs):
        self.last_inputs = inputs
        return {
            "raw_output": "# Test\n\nĐây là một cách thần kỳ và hack với cam kết tuyệt đối.",
            "status": "success",
        }


@pytest.mark.asyncio
async def test_generate_titles_returns_single_feedback_draft():
    service = ContentService(crew=FakeCrew())

    result = await service.generate_titles(["AI blog"])

    assert len(result["titles"]) == 1
    draft = result["titles"][0]
    assert draft["title"] == "Draft 1"
    assert draft["seo_title"] == "Draft SEO"
    assert draft["outline"][0].startswith("## Mo dau")
    assert "- " in draft["outline"][0]


@pytest.mark.asyncio
async def test_generate_content_enforces_style_guide():
    service = ContentService(crew=FakeContentCrew())

    result = await service.generate_content(
        keywords=["AI"],
        selected_title="A practical guide to AI",
        outline=["## Intro\n- Point"],
    )

    assert "thần kỳ" not in result["optimized_content"].lower()
    assert "hack" not in result["optimized_content"].lower()
    assert "hiệu quả" in result["optimized_content"]
    assert result["style_report"]["style_score"] <= 100
    assert len(result["style_report"]["replacements"]) >= 2


def test_extract_single_article_prefers_complete_edited_draft():
    output = """# Draft
## Intro
Original.

# Draft
## Intro
Edited.
## Kết luận
Done.

# Draft
## Intro
Truncated.
"""

    result = ContentService._extract_single_article(output)

    assert result.count("\n# ") == 0
    assert "Edited." in result
    assert "Original." not in result
    assert "Truncated." not in result


def test_build_seo_package_uses_article_content_instead_of_generic_fallback():
    content = """# Cách giữ hơi khi hát

Người mới có thể nhận biết nguyên nhân hụt hơi và luyện luồng hơi đều bằng các bước ngắn, an toàn trong bài viết này.
"""
    package = ContentService.build_seo_package(
        content,
        seo_title="Cách giữ hơi khi hát",
        primary_keyword="giữ hơi khi hát",
        search_intent="informational",
    )

    assert package["meta_description"].startswith("Người mới")
    assert "Blog post about" not in package["meta_description"]
    assert package["suggested_slug"] == "cach-giu-hoi-khi-hat"


def test_brand_profile_replaces_generic_corporate_vocabulary(tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        '{"company_name":"TSS","dictionary":{"allowed_terms":["thanh nhac"],'
        '"forbidden_replacements":{"hoc cap toc":"hoc dung nen tang"}}}',
        encoding="utf-8",
    )
    guide = StyleGuide(
        company_name="Generic",
        allowed_terms=["gia tri kinh doanh"],
        forbidden_replacements={"hack": "phuong phap"},
        style_rules={},
    ).with_brand_voice_profile(profile_path)

    assert guide.allowed_terms == ["thanh nhac"]
    assert guide.forbidden_replacements == {"hoc cap toc": "hoc dung nen tang"}


def test_brand_profile_enforces_forbidden_terms_without_replacements():
    guide = StyleGuide(
        company_name="Generic",
        allowed_terms=[],
        forbidden_replacements={},
        style_rules={},
    ).with_brand_voice_data(
        {
            "company_name": "TSS",
            "vocabulary": {"forbidden_terms": ["Thư giãn"]},
        }
    )

    prompt = guide.to_prompt()
    content, report = guide.enforce("# Bài viết\n\nHãy thư giãn trước khi hát.")

    assert "Do not use 'Thư giãn'" in prompt
    assert content.endswith("Hãy thư giãn trước khi hát.")
    assert report["remaining_forbidden_terms"] == ["Thư giãn"]
    assert report["style_score"] == 75


@pytest.mark.asyncio
async def test_generate_content_uses_selected_project_profile():
    crew = FakeContentCrew()
    repository = type(
        "ProfileRepo",
        (),
        {
            "get": lambda self, project_id, profile_id: {
                "profile_id": profile_id,
                "profile": {
                    "company_name": "Alpha",
                    "dictionary": {"allowed_terms": ["breath support"]},
                    "style_rules": {"tone": "calm and direct"},
                },
            },
            "get_active": lambda self, project_id: None,
        },
    )()
    service = ContentService(crew=crew, profile_repository=repository)

    await service.generate_content(
        keywords=["support"],
        selected_title="A practical guide to support",
        outline=["## Intro"],
        project_id="alpha",
        profile_id="profile-alpha",
    )

    assert "Alpha" in crew.last_inputs["style_guide_instructions"]
    assert "breath support" in crew.last_inputs["style_guide_instructions"]
