"""Content generation business logic."""
from __future__ import annotations

import asyncio
import json
import re
import unicodedata
from typing import Any

from app.agents.llm_factory import LLMFactory
from app.core.exceptions import ContentGenerationError
from app.core.interfaces import ICrew
from app.core.logging import logger
from app.core.style_guide import StyleGuide
from app.repositories.brand_voice_profile_repository import BrandVoiceProfileRepository


class ContentService:
    """Service layer between API routers and Crew orchestration."""

    def __init__(
        self,
        crew: ICrew,
        profile_repository: BrandVoiceProfileRepository | None = None,
    ) -> None:
        self._crew = crew
        settings = getattr(crew, "_settings", None)
        self._settings = settings
        self._profile_repository = profile_repository
        self._style_guide = self._load_style_guide()

    def _load_style_guide(
        self, project_id: str = "default", profile_id: str | None = None
    ) -> StyleGuide:
        style_guide_path = getattr(self._settings, "STYLE_GUIDE_PATH", "./config/corporate_style_guide.json")
        brand_voice_path = getattr(self._settings, "BRAND_VOICE_PROFILE_PATH", "./config/brand_voice_profile.json")
        guide = StyleGuide.from_file(style_guide_path)
        if self._profile_repository is not None:
            stored = (
                self._profile_repository.get(project_id, profile_id)
                if profile_id
                else self._profile_repository.get_active(project_id)
            )
            if stored:
                return guide.with_brand_voice_data(stored["profile"])
        if self._settings is None:
            return guide
        return guide.with_brand_voice_profile(brand_voice_path)

    async def generate_titles(
        self,
        keywords: list[str],
        use_web_search: bool = False,
        project_id: str = "default",
        seo_context: str = "",
    ) -> dict[str, Any]:
        """Run Planner Agent to create one editable draft outline."""
        logger.info("Generating draft plan | keywords={} web_search={}", keywords, use_web_search)

        try:
            result = await asyncio.to_thread(
                self._crew.run,
                inputs={
                    "keywords": ", ".join(keywords),
                    "use_web_search": use_web_search,
                    "project_id": project_id,
                    "seo_context": seo_context,
                },
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
        project_id: str = "default",
        profile_id: str | None = None,
        brief_context: str = "",
    ) -> dict[str, Any]:
        """Run Writer + Editor, then enforce corporate style constraints."""
        logger.info("Generating content | title={}", selected_title)

        try:
            self._style_guide = self._load_style_guide(project_id, profile_id)
            result = await asyncio.to_thread(
                self._crew.run,
                inputs={
                    "keywords": ", ".join(keywords),
                    "selected_title": selected_title,
                    "outline": "\n".join(outline) if outline else "",
                    "use_web_search": use_web_search,
                    "style_guide_instructions": self._style_guide.to_prompt(),
                    "project_id": project_id,
                    "profile_id": profile_id,
                    "brief_context": brief_context,
                },
            )
            raw_output = result.get("raw_output", "")
            logger.info("Raw output length: {} chars | preview: {}", len(raw_output), raw_output[:200])
            raw_output = self._extract_single_article(raw_output)
            result["raw_output"] = raw_output

            title_tag = selected_title
            h1_match = re.search(r"^# (.+)", raw_output, re.MULTILINE)
            if h1_match:
                title_tag = h1_match.group(1).strip()

            optimized_content, style_report = self._style_guide.enforce(raw_output.strip())
            remaining = list(style_report.get("remaining_forbidden_terms") or [])
            if remaining and self._settings is not None:
                logger.warning(
                    "Editor left forbidden terms; requesting targeted repair | terms={}",
                    remaining,
                )
                try:
                    repaired = await self.rewrite_content(
                        optimized_content,
                        "Remove or naturally rewrite every occurrence of these forbidden terms: "
                        + ", ".join(remaining)
                        + ". Preserve the facts, headings, Markdown structure, and article length.",
                        project_id=project_id,
                        profile_id=profile_id,
                    )
                    optimized_content = repaired["rewritten_text"]
                    style_report = repaired["style_report"]
                except ContentGenerationError as exc:
                    logger.warning("Targeted forbidden-term repair failed: {}", exc)

            seo_package = self.build_seo_package(
                optimized_content,
                seo_title=title_tag,
                primary_keyword=keywords[0] if keywords else "",
            )
            parsed_data = {
                "title_tag": title_tag,
                **seo_package,
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

    @classmethod
    def build_seo_package(
        cls,
        content: str,
        *,
        seo_title: str,
        primary_keyword: str = "",
        search_intent: str = "auto",
    ) -> dict[str, str]:
        h1_match = re.search(r"(?m)^#\s+(.+?)\s*$", content)
        final_title = seo_title.strip() or (h1_match.group(1).strip() if h1_match else "")
        return {
            "seo_title": final_title,
            "meta_description": cls._build_meta_description(content, final_title),
            "suggested_slug": cls._suggest_slug(final_title),
            "primary_keyword": primary_keyword,
            "search_intent": search_intent,
        }

    @classmethod
    def _build_meta_description(cls, content: str, title: str) -> str:
        """Build a truthful draft snippet from the article, without keyword stuffing."""
        blocks = [block.strip() for block in re.split(r"\n\s*\n", content) if block.strip()]
        paragraphs = [
            cls._strip_markdown(block)
            for block in blocks
            if not block.startswith("#") and not re.match(r"^[-*]\s", block)
        ]
        source = next((item for item in paragraphs if len(item) >= 60), "")
        if not source:
            source = next((item for item in paragraphs if item), title)
        source = re.sub(r"\s+", " ", source).strip()
        if len(source) <= 180:
            return source
        clipped = source[:181]
        sentence_end = max(clipped.rfind(". "), clipped.rfind("! "), clipped.rfind("? "))
        if sentence_end >= 90:
            return clipped[: sentence_end + 1].strip()
        word_end = clipped.rfind(" ")
        return clipped[:word_end].rstrip(" ,;:-") + "…"

    @staticmethod
    def _strip_markdown(value: str) -> str:
        value = re.sub(r"!?\[([^]]+)]\([^)]+\)", r"\1", value)
        return re.sub(r"[`*_>|~]", "", value).strip()

    @staticmethod
    def _suggest_slug(title: str) -> str:
        normalized = unicodedata.normalize("NFD", title.casefold())
        ascii_like = "".join(
            char for char in normalized if unicodedata.category(char) != "Mn"
        )
        return re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", ascii_like))[:90]

    @staticmethod
    def _extract_single_article(raw_output: str) -> str:
        """Keep the strongest complete article when a small model repeats drafts."""
        cleaned = raw_output.strip()
        fence = re.fullmatch(r"```(?:markdown|md)?\s*(.*?)\s*```", cleaned, re.DOTALL | re.IGNORECASE)
        if fence:
            cleaned = fence.group(1).strip()

        starts = [match.start() for match in re.finditer(r"(?m)^#\s+", cleaned)]
        if len(starts) <= 1:
            return cleaned

        starts.append(len(cleaned))
        candidates = [cleaned[starts[index]:starts[index + 1]].strip() for index in range(len(starts) - 1)]

        def score(article: str) -> tuple[int, int, int]:
            headings = len(re.findall(r"(?m)^##\s+", article))
            complete = int(bool(re.search(r"(?im)^##\s+(kết luận|lời kết|tổng kết)\b", article)))
            return complete, headings, len(article)

        selected = max(candidates, key=score)
        logger.warning(
            "Repeated article output detected | h1_count={} selected_chars={}",
            len(candidates),
            len(selected),
        )
        return selected

    async def rewrite_content(
        self,
        original_text: str,
        feedback: str,
        project_id: str = "default",
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        """Rewrite selected text and enforce the corporate style guide."""
        logger.info("Rewriting content | feedback={}", feedback)

        try:
            self._style_guide = self._load_style_guide(project_id, profile_id)
            llm_factory = LLMFactory(self._crew._settings)
            llm = llm_factory.create(self._crew._settings.EDITOR_MODEL)
            prompt = (
                "You are a senior editor. Rewrite the text according to the user's feedback.\n\n"
                f"Corporate Style Guide:\n{self._style_guide.to_prompt()}\n\n"
                f"Original text:\n{original_text}\n\n"
                f"User feedback:\n{feedback}\n\n"
                "Return only the rewritten text. Do not explain your changes."
            )

            response = await asyncio.to_thread(
                llm.call,
                [{"role": "user", "content": prompt}],
            )
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
