from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BlogEvaluationCase:
    case_id: str
    brief: dict[str, Any]
    actual_output: str
    retrieval_contexts: list[str] = field(default_factory=list)
    reference_output: str | None = None
    brand_profile: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def evaluation_profile(self) -> dict[str, Any]:
        profile = self.brand_profile
        fingerprint = profile.get("writing_fingerprint") or {}
        vocabulary = profile.get("vocabulary") or {}
        return {
            "company_name": profile.get("company_name"),
            "brand_identity": profile.get("brand_identity"),
            "audience_personas": profile.get("audience_personas"),
            "tone": profile.get("tone"),
            "writing_fingerprint": {
                "average_sentence_words": fingerprint.get("average_sentence_words"),
                "active_voice_ratio": fingerprint.get("active_voice_ratio"),
                "preferred_terms": (fingerprint.get("preferred_terms") or [])[:12],
                "forbidden_cliches": fingerprint.get("forbidden_cliches") or [],
                "perspective": fingerprint.get("perspective"),
            },
            "vocabulary": {
                "repeated_terms": (vocabulary.get("repeated_terms") or [])[:12],
                "preferred_phrases": (vocabulary.get("preferred_phrases") or [])[:12],
                "forbidden_terms": vocabulary.get("forbidden_terms") or [],
            },
            "presentation": profile.get("presentation"),
            "rubrics": profile.get("rubrics"),
            "channel_guidelines": profile.get("channel_guidelines"),
        }

    def input_text(self) -> str:
        payload = {
            "brief": self.brief,
            "brand_profile": self.evaluation_profile(),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def ragas_payload(self, max_reference_chars: int = 4000) -> dict[str, Any]:
        reference = self.reference_output
        if reference and len(reference) > max_reference_chars:
            reference = reference[:max_reference_chars]
        return {
            "user_input": self.input_text(),
            "response": self.actual_output,
            "retrieved_contexts": self.retrieval_contexts,
            "reference": reference,
        }
