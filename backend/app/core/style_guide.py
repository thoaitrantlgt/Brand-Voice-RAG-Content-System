"""Corporate style guide loading and deterministic enforcement."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.logging import logger


DEFAULT_STYLE_GUIDE = {
    "company_name": "Company X",
    "dictionary": {
        "allowed_terms": ["AI", "Knowledge Hub", "draft outline"],
        "forbidden_replacements": {},
    },
    "style_rules": {
        "tone": "formal, direct, professional",
        "expertise_level": "business-professional",
        "max_sentence_words": 28,
        "no_jargon": True,
        "writing_principles": [
            "Use clear and concise sentences.",
            "Avoid exaggerated claims.",
        ],
    },
}


@dataclass(frozen=True)
class StyleGuide:
    company_name: str
    allowed_terms: list[str]
    forbidden_replacements: dict[str, str]
    style_rules: dict[str, Any]
    brand_voice_profile: dict[str, Any] | None = None

    @classmethod
    def from_file(cls, path: str | Path) -> "StyleGuide":
        guide_path = Path(path)
        try:
            with guide_path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
        except FileNotFoundError:
            logger.warning("Style guide not found at {}. Falling back to defaults.", guide_path)
            raw = DEFAULT_STYLE_GUIDE

        dictionary = raw.get("dictionary", {})
        return cls(
            company_name=raw.get("company_name", "Company X"),
            allowed_terms=list(dictionary.get("allowed_terms", [])),
            forbidden_replacements=dict(dictionary.get("forbidden_replacements", {})),
            style_rules=dict(raw.get("style_rules", {})),
            brand_voice_profile=raw.get("brand_voice_profile"),
        )

    def with_brand_voice_profile(self, path: str | Path) -> "StyleGuide":
        profile_path = Path(path)
        if not profile_path.exists():
            return self

        try:
            with profile_path.open("r", encoding="utf-8") as f:
                profile = json.load(f)
        except Exception as e:
            logger.warning("Cannot load brand voice profile at {}: {}", profile_path, e)
            return self

        dictionary = profile.get("dictionary", {})
        profile_replacements = {
            str(k): str(v)
            for k, v in dictionary.get("forbidden_replacements", {}).items()
        }
        profile_terms = [str(term) for term in dictionary.get("allowed_terms", [])]

        return StyleGuide(
            company_name=profile.get("company_name") or self.company_name,
            allowed_terms=[*self.allowed_terms, *[t for t in profile_terms if t not in self.allowed_terms]],
            forbidden_replacements={**self.forbidden_replacements, **profile_replacements},
            style_rules={**self.style_rules, **profile.get("style_rules", {})},
            brand_voice_profile=profile,
        )

    def to_prompt(self) -> str:
        forbidden_lines = [
            f"- Do not use '{forbidden}'. Use '{replacement}' instead."
            for forbidden, replacement in self.forbidden_replacements.items()
        ]
        principles = [f"- {item}" for item in self.style_rules.get("writing_principles", [])]
        allowed = ", ".join(self.allowed_terms) if self.allowed_terms else "No explicit allowed terms configured."

        return "\n".join(
            [
                f"You are writing for {self.company_name}. Follow this corporate style guide strictly.",
                f"Tone: {self.style_rules.get('tone', 'formal, direct, professional')}.",
                f"Expertise level: {self.style_rules.get('expertise_level', 'business-professional')}.",
                f"Maximum sentence length: {self.style_rules.get('max_sentence_words', 28)} words.",
                f"Allowed terminology: {allowed}.",
                "Forbidden terminology and required replacements:",
                *(forbidden_lines or ["- No forbidden terms configured."]),
                "Writing principles:",
                *(principles or ["- Be clear, accurate, and concise."]),
                *self._brand_voice_prompt_lines(),
            ]
        )

    def _brand_voice_prompt_lines(self) -> list[str]:
        if not self.brand_voice_profile:
            return []

        profile = self.brand_voice_profile
        vocabulary = profile.get("vocabulary", {})
        presentation = profile.get("presentation", {})
        syntax = profile.get("syntax", {})
        examples = profile.get("examples", [])
        rubrics = profile.get("rubrics", [])
        channel_guidelines = profile.get("channel_guidelines", {})

        lines = [
            "",
            "Learned Brand Voice Profile (hard constraints):",
            f"- Tone profile: {json.dumps(profile.get('tone', {}), ensure_ascii=False)}",
            f"- Syntax profile: {json.dumps(syntax, ensure_ascii=False)}",
            f"- Presentation profile: {json.dumps(presentation, ensure_ascii=False)}",
            f"- Strategic context: {json.dumps(profile.get('strategic_context', {}), ensure_ascii=False)}",
            f"- Channel guidance: {json.dumps(channel_guidelines, ensure_ascii=False)}",
            f"- Preferred vocabulary: {', '.join(vocabulary.get('preferred_phrases', [])[:30]) or 'None detected'}.",
            f"- Repeated terminology to prefer: {', '.join(vocabulary.get('repeated_terms', [])[:50]) or 'None detected'}.",
            "- Brand voice rubrics:",
        ]
        lines.extend(f"  - {item}" for item in rubrics[:12])
        if examples:
            lines.append("- Short reference examples from source blogs:")
            lines.extend(
                f"  - {example.get('text', '')}"
                for example in examples[:6]
                if example.get("text")
            )
        return lines

    def enforce(self, text: str) -> tuple[str, dict[str, Any]]:
        cleaned = text
        replacements: list[dict[str, Any]] = []

        for forbidden, allowed in self.forbidden_replacements.items():
            pattern = re.compile(re.escape(forbidden), re.IGNORECASE)
            cleaned, count = pattern.subn(allowed, cleaned)
            if count:
                replacements.append(
                    {
                        "forbidden": forbidden,
                        "replacement": allowed,
                        "count": count,
                    }
                )

        remaining = self._find_forbidden_terms(cleaned)
        sentence_warnings = self._find_long_sentences(cleaned)
        score = self._score(remaining_count=len(remaining), warning_count=len(sentence_warnings))

        report = {
            "status": "passed" if not remaining else "corrected_with_remaining_violations",
            "style_score": score,
            "replacements": replacements,
            "remaining_forbidden_terms": remaining,
            "sentence_warnings": sentence_warnings,
            "rules": {
                "tone": self.style_rules.get("tone"),
                "expertise_level": self.style_rules.get("expertise_level"),
                "max_sentence_words": self.style_rules.get("max_sentence_words", 28),
            },
        }
        return cleaned, report

    def _find_forbidden_terms(self, text: str) -> list[str]:
        found = []
        for forbidden in self.forbidden_replacements:
            if re.search(re.escape(forbidden), text, re.IGNORECASE):
                found.append(forbidden)
        return found

    def _find_long_sentences(self, text: str) -> list[dict[str, Any]]:
        max_words = int(self.style_rules.get("max_sentence_words", 28))
        warnings = []
        sentences = [s.strip() for s in re.split(r"(?<=[.!?。！？])\s+", text) if s.strip()]

        for sentence in sentences:
            word_count = len(re.findall(r"\S+", sentence))
            if word_count > max_words:
                warnings.append(
                    {
                        "word_count": word_count,
                        "max_words": max_words,
                        "preview": sentence[:160],
                    }
                )

        return warnings[:10]

    @staticmethod
    def _score(remaining_count: int, warning_count: int) -> int:
        score = 100 - remaining_count * 25 - warning_count * 5
        return max(0, min(100, score))
