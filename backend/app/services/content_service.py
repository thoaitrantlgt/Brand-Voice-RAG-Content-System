"""Content generation business logic."""
from __future__ import annotations

import json
import re
from typing import Any

from app.agents.llm_factory import LLMFactory
from app.core.exceptions import ContentGenerationError
from app.core.interfaces import ICrew
from app.core.logging import logger
from app.core.style_guide import StyleGuide


class ContentService:
    """Service layer between API routers and Crew orchestration."""

    def __init__(self, crew: ICrew) -> None:
        self._crew = crew
        settings = getattr(crew, "_settings", None)
        self._settings = settings
        self._style_guide = self._load_style_guide()

    def _load_style_guide(self) -> StyleGuide:
        style_guide_path = getattr(self._settings, "STYLE_GUIDE_PATH", "./config/corporate_style_guide.json")
        brand_voice_path = getattr(self._settings, "BRAND_VOICE_PROFILE_PATH", "./config/brand_voice_profile.json")
        return StyleGuide.from_file(style_guide_path).with_brand_voice_profile(brand_voice_path)

    async def generate_titles(
        self,
        keywords: list[str],
        use_web_search: bool = False,
    ) -> dict[str, Any]:
        """Run Planner Agent to create one editable draft outline."""
        logger.info("Generating draft plan | keywords={} web_search={}", keywords, use_web_search)

        try:
            result = self._crew.run(
                inputs={
                    "keywords": ", ".join(keywords),
                    "use_web_search": use_web_search,
                }
            )
            raw_output = result.get("raw_output", "")
            parsed_data = self._parse_planner_output(raw_output, keywords)
            parsed_data["titles"] = self._normalize_draft_plans(
                parsed_data.get("titles", []),
                fallback_keyword=keywords[0] if keywords else "AI",
            )

            merged = {**result, **parsed_data}
            if result.get("search_links"):
                merged["search_links"] = result["search_links"]
            return merged

        except Exception as e:
            raise ContentGenerationError(
                f"Cannot create draft plan: {e}",
                {"keywords": keywords},
            ) from e

    def _parse_planner_output(self, raw_output: str, keywords: list[str]) -> dict[str, Any]:
        clean_json = ""
        match = re.search(r"```json\s*(.*?)\s*```", raw_output, re.DOTALL)
        if match:
            clean_json = match.group(1)
        else:
            start = raw_output.find("{")
            end = raw_output.rfind("}")
            clean_json = raw_output[start:end + 1] if start != -1 and end != -1 else raw_output.strip()

        clean_json = clean_json.replace("[...]", '["..."]').replace(", ...", "")
        if clean_json.count("[") > clean_json.count("]"):
            clean_json += "]"
        if clean_json.count("{") > clean_json.count("}"):
            clean_json += "}"

        try:
            parsed_data = json.loads(clean_json)
            if not parsed_data.get("titles"):
                raise json.JSONDecodeError("Missing titles", "", 0)
            return parsed_data
        except (json.JSONDecodeError, ValueError):
            logger.error("LLM did not return valid planner JSON: {}", raw_output)
            fallback_keyword = keywords[0] if keywords else "AI"
            return {
                "titles": [
                    {
                        "keyword": fallback_keyword,
                        "title": f"Huong dan chi tiet ve {fallback_keyword}",
                        "seo_title": f"Huong dan chi tiet ve {fallback_keyword}",
                        "outline": [
                            "## Mo dau\n- Boi canh chinh cua chu de\n- Ly do nguoi doc nen quan tam",
                            "## Noi dung chinh\n- Cac luan diem quan trong\n- Du kien hoac vi du ho tro",
                            "## Ket luan\n- Tom tat y chinh\n- Goi y hanh dong tiep theo",
                        ],
                    }
                ]
            }

    def _normalize_draft_plans(
        self,
        titles: list[dict[str, Any]],
        fallback_keyword: str,
    ) -> list[dict[str, Any]]:
        """Keep one editable draft and make outline lines useful for feedback."""
        if not titles:
            titles = [{}]

        plan = titles[0]
        outline = plan.get("outline") or []
        if isinstance(outline, str):
            outline = [line.strip() for line in outline.splitlines() if line.strip()]

        normalized_outline: list[str] = []
        for item in outline:
            text = str(item).strip()
            if not text:
                continue
            if text.startswith("#") or "\n-" in text or "\n* " in text:
                normalized_outline.append(text)
            else:
                normalized_outline.append(f"## {text}\n- Y chinh can trien khai\n- Du kien hoac vi du can bo sung")

        if not normalized_outline:
            normalized_outline = [
                "## Mo dau\n- Boi canh chinh cua chu de\n- Ly do nguoi doc nen quan tam",
                "## Noi dung chinh\n- Cac luan diem quan trong\n- Du kien hoac vi du ho tro",
                "## Ket luan\n- Tom tat y chinh\n- Goi y hanh dong tiep theo",
            ]

        title = plan.get("title") or f"Huong dan chi tiet ve {fallback_keyword}"
        return [
            {
                "keyword": plan.get("keyword") or fallback_keyword,
                "title": title,
                "seo_title": plan.get("seo_title") or title,
                "outline": normalized_outline,
            }
        ]

    async def generate_content(
        self,
        keywords: list[str],
        selected_title: str,
        outline: list[str] | None = None,
        use_web_search: bool = False,
    ) -> dict[str, Any]:
        """Run Writer + Editor, then enforce corporate style constraints."""
        logger.info("Generating content | title={}", selected_title)

        try:
            self._style_guide = self._load_style_guide()
            result = self._crew.run(
                inputs={
                    "keywords": ", ".join(keywords),
                    "selected_title": selected_title,
                    "outline": "\n".join(outline) if outline else "",
                    "use_web_search": use_web_search,
                    "style_guide_instructions": self._style_guide.to_prompt(),
                }
            )
            raw_output = result.get("raw_output", "")
            logger.info("Raw output length: {} chars | preview: {}", len(raw_output), raw_output[:200])

            title_tag = selected_title
            h1_match = re.search(r"^# (.+)", raw_output, re.MULTILINE)
            if h1_match:
                title_tag = h1_match.group(1).strip()

            optimized_content, style_report = self._style_guide.enforce(raw_output.strip())
            parsed_data = {
                "title_tag": title_tag,
                "meta_description": f"Blog post about {', '.join(keywords[:2])}",
                "optimized_content": optimized_content,
                "style_report": style_report,
            }

            logger.info(
                "Final parsed | content={} chars | style_score={}",
                len(parsed_data.get("optimized_content", "")),
                style_report.get("style_score"),
            )
            return {**result, **parsed_data}

        except Exception as e:
            raise ContentGenerationError(
                f"Cannot generate blog content: {e}",
                {"title": selected_title},
            ) from e

    async def rewrite_content(self, original_text: str, feedback: str) -> dict[str, Any]:
        """Rewrite selected text and enforce the corporate style guide."""
        logger.info("Rewriting content | feedback={}", feedback)

        try:
            self._style_guide = self._load_style_guide()
            llm_factory = LLMFactory(self._crew._settings)
            llm = llm_factory.create(self._crew._settings.EDITOR_MODEL)
            prompt = (
                "You are a senior editor. Rewrite the text according to the user's feedback.\n\n"
                f"Corporate Style Guide:\n{self._style_guide.to_prompt()}\n\n"
                f"Original text:\n{original_text}\n\n"
                f"User feedback:\n{feedback}\n\n"
                "Return only the rewritten text. Do not explain your changes."
            )

            response = llm.call([{"role": "user", "content": prompt}])
            rewritten_text, style_report = self._style_guide.enforce(response.strip())
            return {
                "rewritten_text": rewritten_text,
                "style_report": style_report,
                "status": "success",
            }
        except Exception as e:
            raise ContentGenerationError(
                f"Cannot rewrite content: {e}",
                {"feedback": feedback},
            ) from e
