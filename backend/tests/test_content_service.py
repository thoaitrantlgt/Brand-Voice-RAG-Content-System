from app.services.content_service import ContentService
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
