"""Brand voice extraction and profile indexing service."""
from __future__ import annotations

import json
import re
import unicodedata
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.agents.llm_factory import LLMFactory
from app.core.config import Settings
from app.core.exceptions import InvalidInputError, ToolExecutionError
from app.core.interfaces import IVectorStore
from app.core.logging import logger
from app.schemas.document import (
    BrandVoiceEvaluateRequest,
    BrandVoiceEvaluateResponse,
    BrandVoiceProfileResponse,
    TrainBrandVoiceRequest,
)


PROFILE_DOCUMENT_ID = "brand_voice_profile_active"


class BrandVoiceService:
    """Build a brand voice profile from high-quality blog documents already in RAG."""

    def __init__(self, vector_store: IVectorStore, settings: Settings) -> None:
        self._store = vector_store
        self._settings = settings

    async def train(self, request: TrainBrandVoiceRequest) -> BrandVoiceProfileResponse:
        documents = self._load_source_documents(request.document_ids, request.max_documents)
        if not documents:
            raise InvalidInputError(
                "No source blog documents found for brand voice training.",
                {"document_ids": request.document_ids},
            )

        warnings = []
        if len(documents) < request.min_documents:
            warnings.append(
                f"Only {len(documents)} documents were available; 20-30 high-quality blogs are recommended."
            )

        company_name = request.company_name or "Company X"
        analysis = self._extract_with_llm(documents, company_name)
        profile = self._build_profile(analysis, documents, company_name, request)
        profile_markdown = self._profile_to_markdown(profile)

        profile_path = self._write_profile(profile)
        dataset_path = self._write_sft_dataset(documents, profile)
        dpo_dataset_path = self._write_dpo_dataset(documents, profile)
        indexed_chunks = self._index_profile(profile_markdown, profile)

        return BrandVoiceProfileResponse(
            profile_id=profile["profile_id"],
            company_name=company_name,
            source_document_count=len(documents),
            profile_path=str(profile_path),
            dataset_path=str(dataset_path),
            dpo_dataset_path=str(dpo_dataset_path),
            indexed_chunks=indexed_chunks,
            profile_markdown=profile_markdown,
            warnings=warnings,
        )

    async def get_active_profile(self) -> BrandVoiceProfileResponse:
        profile_path = Path(self._settings.BRAND_VOICE_PROFILE_PATH)
        if not profile_path.exists():
            raise InvalidInputError(
                "No brand voice profile has been trained yet.",
                {"profile_path": str(profile_path)},
            )

        with profile_path.open("r", encoding="utf-8") as f:
            profile = json.load(f)

        return BrandVoiceProfileResponse(
            profile_id=profile.get("profile_id", PROFILE_DOCUMENT_ID),
            company_name=profile.get("company_name", "Company X"),
            source_document_count=int(profile.get("source_document_count", 0)),
            profile_path=str(profile_path),
            dataset_path=profile.get("dataset_path"),
            dpo_dataset_path=profile.get("dpo_dataset_path"),
            indexed_chunks=int(profile.get("indexed_chunks", 0)),
            profile_markdown=self._profile_to_markdown(profile),
            warnings=[],
        )

    async def evaluate(self, request: BrandVoiceEvaluateRequest) -> BrandVoiceEvaluateResponse:
        profile_path = Path(self._settings.BRAND_VOICE_PROFILE_PATH)
        if not profile_path.exists():
            raise InvalidInputError(
                "No brand voice profile has been trained yet.",
                {"profile_path": str(profile_path)},
            )

        with profile_path.open("r", encoding="utf-8") as f:
            profile = json.load(f)

        scores, violations, recommendations = self._score_content_against_profile(
            request.content,
            profile,
            request.channel,
            request.persona_name,
        )
        heuristic_overall = round(sum(scores.values()) / max(1, len(scores)))
        llm_judge = None
        evaluation_method = "heuristic"
        overall = heuristic_overall

        if request.use_llm_judge:
            llm_judge = self._judge_with_llm(request.content, profile, request.channel, request.persona_name)
            if llm_judge:
                llm_score = int(llm_judge.get("overall_score", heuristic_overall))
                overall = round((heuristic_overall + llm_score) / 2)
                scores["llm_judge"] = max(0, min(100, llm_score))
                violations.extend(str(item) for item in llm_judge.get("violations", []) if item)
                recommendations.extend(str(item) for item in llm_judge.get("recommendations", []) if item)
                evaluation_method = "heuristic_plus_llm_judge"
            else:
                recommendations.append("LLM judge was requested but unavailable; heuristic evaluation was used.")

        return BrandVoiceEvaluateResponse(
            profile_id=profile.get("profile_id", PROFILE_DOCUMENT_ID),
            channel=request.channel,
            content_type=request.content_type,
            overall_score=overall,
            dimension_scores=scores,
            llm_judge=llm_judge,
            evaluation_method=evaluation_method,
            violations=violations,
            recommendations=recommendations,
            reviewer_checklist=profile.get("governance", {}).get("reviewer_checklist", []),
        )

    def score_content_against_profile(
        self,
        content: str,
        profile: dict[str, Any],
        channel: str = "blog",
        persona_name: str | None = None,
    ) -> dict[str, Any]:
        scores, violations, recommendations, score_breakdown = self._score_content_against_profile(
            content, profile, channel, persona_name, include_breakdown=True
        )
        return {
            "dimension_scores": scores,
            "score_breakdown": score_breakdown,
            "violations": violations,
            "recommendations": recommendations,
            "selected_persona": self._select_persona(
                profile.get("audience_personas", []), persona_name
            ),
        }

    def _load_source_documents(
        self,
        document_ids: list[str],
        max_documents: int,
    ) -> list[dict[str, Any]]:
        chunks = self._store.get_documents()
        selected_ids = set(document_ids)
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for chunk in chunks:
            meta = chunk.get("metadata", {})
            doc_id = str(meta.get("document_id") or "")
            if not doc_id or doc_id == PROFILE_DOCUMENT_ID:
                continue
            if meta.get("content_type") == "brand_voice_profile":
                continue
            purpose = str(meta.get("purpose") or "knowledge")
            if not selected_ids and purpose not in ("brand_voice", "both"):
                continue
            if selected_ids and doc_id not in selected_ids:
                continue
            grouped[doc_id].append(chunk)

        documents = []
        for doc_id, doc_chunks in grouped.items():
            ordered = sorted(
                doc_chunks,
                key=lambda item: int(str(item.get("metadata", {}).get("chunk_index", 0)) or 0),
            )
            filename = ordered[0].get("metadata", {}).get("filename", doc_id)
            text = "\n\n".join(chunk.get("text", "") for chunk in ordered if chunk.get("text"))
            if text.strip():
                documents.append({
                    "document_id": doc_id,
                    "filename": filename,
                    "text": text.strip(),
                })

        return documents[:max_documents]

    def _extract_with_llm(
        self,
        documents: list[dict[str, Any]],
        company_name: str,
    ) -> dict[str, Any]:
        prompt = self._build_extraction_prompt(documents, company_name)
        try:
            llm = LLMFactory(self._settings).create(self._settings.EDITOR_MODEL)
            response = llm.call([{"role": "user", "content": prompt}])
            return self._parse_json(response)
        except Exception as e:
            logger.warning("Brand voice LLM extraction failed; using deterministic fallback | {}", e)
            return self._fallback_analysis(documents)

    def _build_extraction_prompt(self, documents: list[dict[str, Any]], company_name: str) -> str:
        samples = []
        for index, document in enumerate(documents, 1):
            samples.append(
                f"--- BLOG {index}: {document['filename']} ---\n"
                f"{document['text'][:6000]}"
            )

        return (
            "You are an Extraction Agent. Analyze these complete blog posts and extract the company's brand voice.\n"
            f"Company: {company_name}\n\n"
            "Return only valid JSON with this schema:\n"
            "{\n"
            '  "brand_identity": {"mission": "", "vision": "", "positioning": "", "personality_traits": [], "differentiators": []},\n'
            '  "audience_personas": [{"name": "", "priorities": [], "tone_adjustment": "", "decision_criteria": []}],\n'
            '  "writing_fingerprint": {\n'
            '    "sentence_patterns": {"average_sentence_words": 0, "short_fragment_ratio": 0, "rhetorical_question_ratio": 0, "dash_usage_per_1000_words": 0, "parenthetical_aside_ratio": 0, "preferred_structures": []},\n'
            '    "vocabulary_fingerprints": {"preferred_terms": [], "transition_phrases": [], "forbidden_cliches": []},\n'
            '    "perspective_matching": {"self_reference": "", "reader_address": "", "stance": "", "argument_style": ""}\n'
            '  },\n'
            '  "tone": {"primary": "", "secondary": [], "description": ""},\n'
            '  "vocabulary": {"repeated_terms": [], "preferred_phrases": [], "forbidden_terms": [], "replacements": {}},\n'
            '  "syntax": {"sentence_style": "", "average_sentence_words": 0, "rules": []},\n'
            '  "presentation": {"heading_style": "", "list_style": "", "chart_intro_style": "", "rules": []},\n'
            '  "do_dont_examples": {"do": [], "dont": []},\n'
            '  "examples": [{"category": "", "text": "", "source": ""}],\n'
            '  "rubrics": []\n'
            "}\n\n"
            "Use direct examples from the supplied blogs, but keep each example short.\n\n"
            + "\n\n".join(samples)
        )

    def _parse_json(self, raw: str) -> dict[str, Any]:
        match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
        payload = match.group(1) if match else raw
        start = payload.find("{")
        end = payload.rfind("}")
        if start != -1 and end != -1:
            payload = payload[start:end + 1]
        return json.loads(payload)

    def _fallback_analysis(self, documents: list[dict[str, Any]]) -> dict[str, Any]:
        all_text = "\n\n".join(document["text"] for document in documents)
        words = re.findall(r"[A-Za-zÀ-ỹ][A-Za-zÀ-ỹ0-9_-]{2,}", all_text.lower())
        stopwords = {
            "cua", "cho", "voi", "cac", "nhung", "trong", "mot", "the", "and", "for",
            "that", "this", "are", "was", "were", "from", "ban", "nguoi", "khong",
        }
        terms = [
            word for word, _ in Counter(words).most_common(40)
            if word not in stopwords and len(word) > 3
        ][:20]
        sentences = re.split(r"(?<=[.!?。！？])\s+", all_text)
        sentence_lengths = [len(re.findall(r"\S+", sentence)) for sentence in sentences if sentence.strip()]
        avg_words = round(sum(sentence_lengths) / len(sentence_lengths), 1) if sentence_lengths else 0
        examples = []
        for document in documents[:8]:
            first_sentence = next((s.strip() for s in re.split(r"(?<=[.!?。！？])\s+", document["text"]) if len(s.strip()) > 40), "")
            if first_sentence:
                examples.append({
                    "category": "representative_sentence",
                    "text": first_sentence[:240],
                    "source": document["filename"],
                })
        writing_fingerprint = self._extract_writing_fingerprint(
            documents,
            preferred_terms=terms[:12],
        )

        return {
            "tone": {
                "primary": "professional",
                "secondary": ["clear", "helpful"],
                "description": "Inferred from source articles by deterministic fallback.",
            },
            "vocabulary": {
                "repeated_terms": terms,
                "preferred_phrases": terms[:8],
                "forbidden_terms": [],
                "replacements": {},
            },
            "syntax": {
                "sentence_style": "concise" if avg_words <= 24 else "expanded",
                "average_sentence_words": avg_words,
                "rules": ["Keep sentences close to the learned average length."],
            },
            "presentation": {
                "heading_style": "Preserve the source blogs' Markdown heading hierarchy.",
                "list_style": "Use lists when the source articles use scannable steps or criteria.",
                "chart_intro_style": "Introduce charts with a short insight before the visual.",
                "rules": ["Keep introduction, body, and conclusion structure intact."],
            },
            "brand_identity": {
                "mission": "Help readers make practical decisions with clear expert guidance.",
                "vision": "Become a trusted source for useful, accurate, and actionable content.",
                "positioning": "Expert advisor that explains complex topics without hype.",
                "personality_traits": ["clear", "practical", "credible"],
                "differentiators": ["plain-language explanations", "evidence-led recommendations"],
            },
            "audience_personas": [
                {
                    "name": "Business reader",
                    "priorities": ["clarity", "business impact", "next steps"],
                    "tone_adjustment": "Practical and concise.",
                    "decision_criteria": ["specificity", "accuracy", "usefulness"],
                }
            ],
            "writing_fingerprint": writing_fingerprint,
            "do_dont_examples": {
                "do": ["Explain the point plainly before adding nuance."],
                "dont": ["Do not rely on generic hype or unsupported superlatives."],
            },
            "examples": examples,
            "rubrics": [
                "Match the learned tone before optimizing for SEO.",
                "Reuse preferred terminology consistently.",
                "Avoid claims that are not supported by retrieved context.",
            ],
        }

    def _build_profile(
        self,
        analysis: dict[str, Any],
        documents: list[dict[str, Any]],
        company_name: str,
        request: TrainBrandVoiceRequest,
    ) -> dict[str, Any]:
        profile_id = f"brand_voice_{uuid.uuid4().hex[:12]}"
        vocabulary = analysis.get("vocabulary", {})
        source_count = len(documents)
        repeated_terms = vocabulary.get("repeated_terms", [])[:50]
        preferred_phrases = vocabulary.get("preferred_phrases", [])[:30]
        rubrics = analysis.get("rubrics", [])
        brand_identity = self._build_brand_identity(analysis, company_name, request)
        audience_personas = self._build_audience_personas(analysis, request)
        writing_fingerprint = self._build_writing_fingerprint(analysis, documents, preferred_phrases)
        return {
            "profile_id": profile_id,
            "version": "2.2",
            "company_name": company_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_document_count": source_count,
            "source_documents": [
                {"document_id": doc["document_id"], "filename": doc["filename"]}
                for doc in documents
            ],
            "brand_identity": brand_identity,
            "audience_personas": audience_personas,
            "writing_fingerprint": writing_fingerprint,
            "strategic_context": {
                "target_audience": request.target_audience or "Primary blog readers and prospective customers.",
                "brand_values": request.brand_values,
                "mission": brand_identity.get("mission"),
                "vision": brand_identity.get("vision"),
                "positioning": brand_identity.get("positioning"),
                "interaction_style": "Expert advisor with clear, practical guidance.",
                "message_architecture": [
                    "Lead with the reader's problem.",
                    "Explain the point plainly before adding nuance.",
                    "Close with a practical next step.",
                ],
            },
            "tone": analysis.get("tone", {}),
            "vocabulary": vocabulary,
            "syntax": analysis.get("syntax", {}),
            "presentation": analysis.get("presentation", {}),
            "do_dont_examples": analysis.get("do_dont_examples", {}),
            "examples": analysis.get("examples", []),
            "rubrics": rubrics,
            "channel_guidelines": self._build_channel_guidelines(request.channels),
            "prompt_templates": self._build_prompt_templates(company_name),
            "calibration_tests": self._build_calibration_tests(company_name),
            "training_method_recommendation": self._recommend_training_method(source_count),
            "governance": self._build_governance_plan(),
            "dictionary": {
                "allowed_terms": repeated_terms,
                "forbidden_replacements": vocabulary.get("replacements", {}),
            },
            "style_rules": {
                "tone": analysis.get("tone", {}).get("description") or analysis.get("tone", {}).get("primary", ""),
                "expertise_level": "brand-specific",
                "max_sentence_words": max(12, int(float(analysis.get("syntax", {}).get("average_sentence_words") or 28) * 1.4)),
                "writing_principles": rubrics,
                "preferred_phrases": preferred_phrases,
                "personality_traits": brand_identity.get("personality_traits", []),
                "writing_fingerprint": writing_fingerprint,
            },
        }

    def _build_writing_fingerprint(
        self,
        analysis: dict[str, Any],
        documents: list[dict[str, Any]],
        preferred_terms: list[str],
    ) -> dict[str, Any]:
        measured = self._extract_writing_fingerprint(documents, preferred_terms=preferred_terms)
        extracted = analysis.get("writing_fingerprint") or {}
        if not isinstance(extracted, dict):
            return measured

        return {
            "sentence_patterns": {
                **measured.get("sentence_patterns", {}),
                **{
                    key: value
                    for key, value in (extracted.get("sentence_patterns") or {}).items()
                    if value not in (None, "", [])
                },
            },
            "vocabulary_fingerprints": {
                **measured.get("vocabulary_fingerprints", {}),
                **{
                    key: value
                    for key, value in (extracted.get("vocabulary_fingerprints") or {}).items()
                    if value not in (None, "", [])
                },
            },
            "perspective_matching": {
                **measured.get("perspective_matching", {}),
                **{
                    key: value
                    for key, value in (extracted.get("perspective_matching") or {}).items()
                    if value not in (None, "", [])
                },
            },
        }

    def _extract_writing_fingerprint(
        self,
        documents: list[dict[str, Any]],
        preferred_terms: list[str] | None = None,
    ) -> dict[str, Any]:
        text = "\n\n".join(document.get("text", "") for document in documents)
        metrics = self._text_style_metrics(text)
        transition_phrases = self._find_transition_phrases(text)
        perspective = self._infer_perspective(text)

        preferred_structures = []
        if metrics["short_fragment_ratio"] >= 0.08:
            preferred_structures.append("Uses short fragments for emphasis.")
        if metrics["rhetorical_question_ratio"] >= 0.05:
            preferred_structures.append("Uses rhetorical questions to open or turn paragraphs.")
        if metrics["dash_usage_per_1000_words"] >= 2:
            preferred_structures.append("Uses dashes to add asides or sharpen contrast.")
        if metrics["parenthetical_aside_ratio"] >= 0.03:
            preferred_structures.append("Uses parenthetical asides for nuance.")
        if not preferred_structures:
            preferred_structures.append("Uses balanced explanatory sentences with restrained punctuation.")

        return {
            "sentence_patterns": {
                **metrics,
                "preferred_structures": preferred_structures,
            },
            "vocabulary_fingerprints": {
                "preferred_terms": self._dedupe_strings(preferred_terms or [])[:30],
                "transition_phrases": transition_phrases,
                "forbidden_cliches": [
                    "trong kỷ nguyên số",
                    "đột phá",
                    "toàn diện",
                    "đỉnh cao",
                    "hành trình",
                    "cam kết",
                    "đáng chú ý",
                    "tóm lại",
                    "in the digital age",
                    "game-changing",
                    "revolutionary",
                ],
            },
            "perspective_matching": perspective,
        }

    def _text_style_metrics(self, text: str) -> dict[str, Any]:
        sentences = self._split_sentences(text)
        sentence_lengths = [self._word_count(sentence) for sentence in sentences]
        total_sentences = max(1, len(sentence_lengths))
        total_words = max(1, self._word_count(text))
        short_fragments = [
            sentence for sentence, length in zip(sentences, sentence_lengths)
            if 2 <= length <= 4
        ]
        rhetorical_questions = [sentence for sentence in sentences if sentence.rstrip().endswith("?")]
        parenthetical_asides = re.findall(r"\([^)]{3,160}\)", text)
        dash_count = text.count("—") + text.count("–") + len(re.findall(r"\s-\s", text))
        passive_markers = [" được ", " bị ", " was ", " were ", " is being ", " are being "]
        passive_sentences = [
            sentence for sentence in sentences
            if any(marker in f" {sentence.lower()} " for marker in passive_markers)
        ]

        punctuation_counts = {
            "comma": text.count(","),
            "semicolon": text.count(";"),
            "colon": text.count(":"),
            "dash": dash_count,
            "parentheses": len(parenthetical_asides),
            "question_mark": text.count("?"),
            "exclamation_mark": text.count("!"),
        }
        punctuation_per_1000_words = {
            key: round(value / total_words * 1000, 2)
            for key, value in punctuation_counts.items()
        }

        avg_words = round(sum(sentence_lengths) / total_sentences, 1) if sentence_lengths else 0
        active_voice_ratio = round(1 - (len(passive_sentences) / total_sentences), 2)

        return {
            "average_sentence_words": avg_words,
            "short_fragment_ratio": round(len(short_fragments) / total_sentences, 3),
            "rhetorical_question_ratio": round(len(rhetorical_questions) / total_sentences, 3),
            "dash_usage_per_1000_words": round(dash_count / total_words * 1000, 2),
            "parenthetical_aside_ratio": round(len(parenthetical_asides) / total_sentences, 3),
            "active_voice_ratio": max(0, min(1, active_voice_ratio)),
            "punctuation_per_1000_words": punctuation_per_1000_words,
            "short_fragment_examples": short_fragments[:8],
        }

    def _infer_perspective(self, text: str) -> dict[str, Any]:
        lowered = f" {text.lower()} "
        self_reference_options = {
            "tôi": [" tôi ", " toi ", " mình ", " minh ", " i "],
            "chúng tôi": [" chúng tôi ", " chung toi ", " we ", " our "],
            "chúng ta": [" chúng ta ", " chung ta ", " us "],
        }
        reader_options = {
            "bạn": [" bạn ", " ban ", " you ", " your "],
            "anh em": [" anh em "],
            "developer": [" developer", " developers", " dev "],
            "team": [" team ", " teams "],
        }
        stance_markers = {
            "mentor": ["hãy", "nen", "nên", "can", "cần", "here is", "you should"],
            "peer": ["mình", "minh", "chúng ta", "cung nhau", "together", "we"],
            "contrarian": ["không hẳn", "khong han", "nghe thì", "nghe thi", "nhưng thực tế", "but in practice", "however"],
        }

        if any(marker in lowered for marker in self_reference_options["chúng tôi"]):
            self_reference = "chúng tôi"
        elif any(marker in lowered for marker in self_reference_options["chúng ta"]):
            self_reference = "chúng ta"
        else:
            self_reference = self._best_marker_label(
                lowered, self_reference_options, fallback="unspecified"
            )
        reader_address = self._best_marker_label(lowered, reader_options, fallback="reader")
        stance = self._best_marker_label(lowered, stance_markers, fallback="mentor")
        argument_style = "balanced_with_counterpoints" if stance == "contrarian" else "explain_then_recommend"

        return {
            "self_reference": self_reference,
            "reader_address": reader_address,
            "stance": stance,
            "argument_style": argument_style,
        }

    def _find_transition_phrases(self, text: str) -> list[str]:
        lowered = text.lower()
        candidates = [
            "thực ra thì",
            "thuc ra thi",
            "có điều",
            "co dieu",
            "nhưng thực tế là",
            "nhung thuc te la",
            "không hẳn",
            "khong han",
            "nghe thì hay",
            "nghe thi hay",
            "nhìn lại xem",
            "nhin lai xem",
            "cơ mà",
            "co ma",
            "however",
            "in practice",
            "the point is",
            "that said",
        ]
        found = [
            (phrase, lowered.count(phrase))
            for phrase in candidates
            if phrase in lowered
        ]
        found.sort(key=lambda item: item[1], reverse=True)
        return [phrase for phrase, _ in found[:12]]

    def _split_sentences(self, text: str) -> list[str]:
        candidates = re.split(r"(?<=[.!?。！？])\s+|\n{2,}", text)
        return [
            sentence.strip()
            for sentence in candidates
            if self._word_count(sentence) > 0
        ]

    @staticmethod
    def _word_count(text: str) -> int:
        return len(re.findall(r"\b[\w'-]+\b", text, flags=re.UNICODE))

    @staticmethod
    def _best_marker_label(
        text: str,
        options: dict[str, list[str]],
        fallback: str,
    ) -> str:
        scores = {
            label: sum(text.count(marker) for marker in markers)
            for label, markers in options.items()
        }
        label, score = max(scores.items(), key=lambda item: item[1])
        return label if score > 0 else fallback

    def _build_brand_identity(
        self,
        analysis: dict[str, Any],
        company_name: str,
        request: TrainBrandVoiceRequest,
    ) -> dict[str, Any]:
        extracted = dict(analysis.get("brand_identity") or {})
        explicit = request.brand_identity.model_dump(exclude_none=True) if request.brand_identity else {}

        identity = {
            "company_name": company_name,
            "mission": "Help customers make confident decisions with practical expertise.",
            "vision": "Become a trusted voice in the market.",
            "positioning": "Expert advisor with clear, grounded communication.",
            "value_proposition": "Clear guidance that turns complex topics into practical next steps.",
            "brand_archetype": "advisor",
            "personality_traits": ["clear", "credible", "practical"],
            "differentiators": ["plain-language expertise", "actionable recommendations"],
            "taboo_topics": [],
        }
        identity.update({k: v for k, v in extracted.items() if v})
        identity.update({k: v for k, v in explicit.items() if v not in (None, [], "")})
        identity["personality_traits"] = self._dedupe_strings(identity.get("personality_traits", []))[:12]
        identity["differentiators"] = self._dedupe_strings(identity.get("differentiators", []))[:12]
        identity["taboo_topics"] = self._dedupe_strings(identity.get("taboo_topics", []))[:12]
        return identity

    def _build_audience_personas(
        self,
        analysis: dict[str, Any],
        request: TrainBrandVoiceRequest,
    ) -> list[dict[str, Any]]:
        if request.audience_personas:
            return [persona.model_dump(exclude_none=True) for persona in request.audience_personas]

        extracted = analysis.get("audience_personas") or []
        if isinstance(extracted, list) and extracted:
            return [persona for persona in extracted[:8] if isinstance(persona, dict)]

        return [
            {
                "name": "Primary blog reader",
                "segment": "prospective_customer",
                "priorities": ["clarity", "credibility", "business impact"],
                "knowledge_level": "business-professional",
                "tone_adjustment": "Helpful, direct, and practical.",
                "preferred_channels": ["blog", "email"],
                "decision_criteria": ["specific examples", "clear next steps", "credible claims"],
            }
        ]

    def _build_channel_guidelines(self, channels: list[str]) -> dict[str, dict[str, Any]]:
        defaults = {
            "blog": {
                "role": "Content Marketing Manager",
                "voice_adjustment": "Helpful, structured, and practical.",
                "rules": ["Use clear H2/H3 sections.", "Keep introduction, body, and conclusion complete."],
            },
            "email": {
                "role": "Email Marketing Specialist",
                "voice_adjustment": "Personal, concise, and action-oriented.",
                "rules": ["Use a clear subject line.", "Keep one primary CTA.", "Avoid dense paragraphs."],
            },
            "social": {
                "role": "Social Media Manager",
                "voice_adjustment": "Sharper and more conversational while staying on-brand.",
                "rules": ["Lead with a strong hook.", "Use platform-native brevity.", "Avoid unsupported hype."],
            },
            "support": {
                "role": "Customer Support Specialist",
                "voice_adjustment": "Empathetic, calm, and solution-focused.",
                "rules": ["Acknowledge the issue.", "Explain the next step.", "Avoid humor in sensitive cases."],
            },
            "ads": {
                "role": "Performance Copywriter",
                "voice_adjustment": "Punchy, specific, and benefit-led.",
                "rules": ["Make the offer concrete.", "Avoid vague superlatives.", "Keep claims verifiable."],
            },
        }
        selected = channels or list(defaults)
        return {channel: defaults.get(channel, defaults["blog"]) for channel in selected}

    def _build_prompt_templates(self, company_name: str) -> dict[str, str]:
        return {
            "blog": (
                f"You are a Content Writer for {company_name}. Write a Vietnamese blog post about {{topic}}. "
                "Follow the Brand Voice Profile, use preferred vocabulary, avoid forbidden terms, "
                "and structure the answer with H1, H2, body sections, and a useful conclusion."
            ),
            "support": (
                f"You are a Customer Support Specialist for {company_name}. Respond to {{customer_issue}}. "
                "Stay empathetic and solution-focused, acknowledge the concern, explain the next step, "
                "and keep the response concise."
            ),
            "social": (
                f"You are a Social Media Manager for {company_name}. Create a post about {{topic}}. "
                "Keep the brand personality recognizable, use one strong hook, and avoid generic AI-sounding phrasing."
            ),
        }

    def _build_calibration_tests(self, company_name: str) -> list[dict[str, str]]:
        prompts = [
            ("blog_intro", "Write an introduction for a blog post about improving content consistency."),
            ("blog_outline", "Create a blog outline for a new product education article."),
            ("support_reply", "Reply to a customer who is frustrated about a delayed feature."),
            ("email_subject", "Write five email subject lines for a product update."),
            ("newsletter_opening", "Write the opening paragraph for a monthly newsletter."),
            ("social_post", "Write a LinkedIn post about a practical industry lesson."),
            ("ad_variation", "Write three short ad variations for a service page."),
            ("product_description", "Describe a product feature for a skeptical buyer."),
            ("case_study_summary", "Summarize a customer success story in the brand voice."),
            ("thought_leadership", "Write a short point of view on an industry trend."),
        ]
        return [
            {
                "id": key,
                "prompt": f"For {company_name}: {prompt}",
                "scoring_focus": "tone, vocabulary, sentence rhythm, factual accuracy, channel fit",
            }
            for key, prompt in prompts
        ]

    def _recommend_training_method(self, source_count: int) -> dict[str, Any]:
        if source_count < 5:
            method = "prompt_engineering"
            rationale = "Not enough examples for reliable RAG or fine-tuning; start with prompt templates and a reviewed guide."
        elif source_count < 30:
            method = "prompt_engineering_plus_examples"
            rationale = "Enough examples for few-shot prompting, but below the recommended RAG library size."
        elif source_count < 500:
            method = "rag"
            rationale = "Enough documents to retrieve brand guidance and approved examples dynamically."
        elif source_count < 10000:
            method = "peft"
            rationale = "A larger labeled set could support adapter-based fine-tuning."
        else:
            method = "full_fine_tuning"
            rationale = "Large enterprise-scale data may justify full fine-tuning if governance and budget exist."

        return {
            "recommended_method": method,
            "rationale": rationale,
            "method_ladder": [
                "prompt_engineering",
                "rag",
                "peft",
                "full_fine_tuning",
            ],
        }

    def _build_governance_plan(self) -> dict[str, Any]:
        return {
            "review_cadence": "Monthly for the first three months, then quarterly.",
            "versioning": "Increment the profile version whenever rubrics, forbidden terms, or examples change.",
            "reviewer_checklist": [
                "Tone matches the Brand Voice Profile for the chosen channel.",
                "Preferred terms are used consistently.",
                "Forbidden or off-brand phrases are absent.",
                "Sentence rhythm and readability match the learned profile.",
                "Factual claims are supported by source material or human review.",
                "The content has a clear next step and does not sound generic.",
            ],
            "raci": {
                "generate_draft": {"content_creator": "R", "marketing_manager": "I", "brand_lead": "I"},
                "brand_review": {"content_creator": "R", "marketing_manager": "C", "brand_lead": "A"},
                "fact_check": {"content_creator": "R", "marketing_manager": "C", "brand_lead": "I"},
                "profile_updates": {"content_creator": "C", "marketing_manager": "R", "brand_lead": "A"},
            },
            "measurement": [
                "Voice deviation score from /brand-voice/evaluate.",
                "Recurring forbidden term or vocabulary violations.",
                "Reviewer notes on off-brand patterns.",
                "Performance comparison against human-written content.",
            ],
        }

    def _profile_to_markdown(self, profile: dict[str, Any]) -> str:
        vocabulary = profile.get("vocabulary", {})
        presentation = profile.get("presentation", {})
        syntax = profile.get("syntax", {})
        examples = profile.get("examples", [])
        do_dont = profile.get("do_dont_examples", {})
        writing_fingerprint = profile.get("writing_fingerprint", {})

        lines = [
            f"# Brand Voice Profile: {profile.get('company_name', 'Company X')}",
            "",
            f"Version: {profile.get('version', '1.0')}",
            f"Profile ID: {profile.get('profile_id', PROFILE_DOCUMENT_ID)}",
            f"Source documents: {profile.get('source_document_count', 0)}",
            f"Recommended method: {profile.get('training_method_recommendation', {}).get('recommended_method', 'unknown')}",
            "",
            "## Brand Identity",
            json.dumps(profile.get("brand_identity", {}), ensure_ascii=False, indent=2),
            "",
            "## Audience Personas",
            json.dumps(profile.get("audience_personas", []), ensure_ascii=False, indent=2),
            "",
            "## Writing Fingerprint",
            json.dumps(writing_fingerprint, ensure_ascii=False, indent=2),
            "",
            "## Strategic Context",
            json.dumps(profile.get("strategic_context", {}), ensure_ascii=False, indent=2),
            "",
            "## Tone",
            json.dumps(profile.get("tone", {}), ensure_ascii=False, indent=2),
            "",
            "## Vocabulary",
            f"Repeated terms: {', '.join(vocabulary.get('repeated_terms', [])[:50]) or 'Not detected'}",
            f"Preferred phrases: {', '.join(vocabulary.get('preferred_phrases', [])[:30]) or 'Not detected'}",
            f"Forbidden terms: {', '.join(vocabulary.get('forbidden_terms', [])[:30]) or 'None configured'}",
            "",
            "## Syntax",
            json.dumps(syntax, ensure_ascii=False, indent=2),
            "",
            "## Presentation",
            json.dumps(presentation, ensure_ascii=False, indent=2),
            "",
            "## Do / Don't Examples",
            "Do:",
        ]
        lines.extend(f"- {item}" for item in do_dont.get("do", []))
        lines.extend(["", "Don't:"])
        lines.extend(f"- {item}" for item in do_dont.get("dont", []))
        lines.extend([
            "",
            "## Channel Guidelines",
            json.dumps(profile.get("channel_guidelines", {}), ensure_ascii=False, indent=2),
            "",
            "## Calibration Tests",
        ])
        lines.extend(
            f"- {item.get('id')}: {item.get('prompt')}"
            for item in profile.get("calibration_tests", [])
        )
        lines.extend([
            "",
            "## Rubrics",
        ])
        lines.extend(f"- {item}" for item in profile.get("rubrics", []))
        lines.extend(["", "## Governance"])
        lines.extend(f"- {item}" for item in profile.get("governance", {}).get("reviewer_checklist", []))
        lines.extend(["", "## Prompt Templates"])
        for name, template in profile.get("prompt_templates", {}).items():
            lines.append(f"- {name}: {template}")
        lines.extend(["", "## Examples"])
        for example in examples[:12]:
            lines.append(f"- ({example.get('category', 'example')}, {example.get('source', 'unknown')}) {example.get('text', '')}")
        return "\n".join(lines).strip()

    def _write_profile(self, profile: dict[str, Any]) -> Path:
        profile_path = Path(self._settings.BRAND_VOICE_PROFILE_PATH)
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        with profile_path.open("w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        return profile_path

    def _write_sft_dataset(self, documents: list[dict[str, Any]], profile: dict[str, Any]) -> Path:
        dataset_dir = Path(self._settings.BRAND_VOICE_DATASET_DIR)
        dataset_dir.mkdir(parents=True, exist_ok=True)
        dataset_path = dataset_dir / "brand_voice_sft.jsonl"

        with dataset_path.open("w", encoding="utf-8") as f:
            for document in documents:
                title = document["text"].splitlines()[0].strip("# ").strip()[:180] or document["filename"]
                row = {
                    "messages": [
                        {
                            "role": "system",
                            "content": "Write Vietnamese blog content that follows the supplied Brand Voice Profile.",
                        },
                        {
                            "role": "user",
                            "content": f"Create a complete blog post titled: {title}",
                        },
                        {
                            "role": "assistant",
                            "content": document["text"],
                        },
                    ],
                    "metadata": {
                        "source_document_id": document["document_id"],
                        "source_filename": document["filename"],
                        "brand_voice_profile_id": profile["profile_id"],
                    },
                }
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        profile["dataset_path"] = str(dataset_path)
        return dataset_path

    def _write_dpo_dataset(self, documents: list[dict[str, Any]], profile: dict[str, Any]) -> Path:
        dataset_dir = Path(self._settings.BRAND_VOICE_DATASET_DIR)
        dataset_dir.mkdir(parents=True, exist_ok=True)
        dataset_path = dataset_dir / "brand_voice_dpo_seed.jsonl"

        with dataset_path.open("w", encoding="utf-8") as f:
            for document in documents:
                title = document["text"].splitlines()[0].strip("# ").strip()[:180] or document["filename"]
                chosen = document["text"]
                rejected = self._make_generic_rejected_example(title)
                row = {
                    "prompt": f"Write a complete Vietnamese blog post titled: {title}",
                    "chosen": chosen,
                    "rejected": rejected,
                    "metadata": {
                        "source_document_id": document["document_id"],
                        "source_filename": document["filename"],
                        "brand_voice_profile_id": profile["profile_id"],
                        "note": "Seed preference pair. Review before production DPO training.",
                    },
                }
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        profile["dpo_dataset_path"] = str(dataset_path)
        return dataset_path

    def _make_generic_rejected_example(self, title: str) -> str:
        return (
            f"# {title}\n\n"
            "Trong thời đại số, chủ đề này ngày càng trở nên quan trọng đối với mọi doanh nghiệp. "
            "Bài viết này sẽ khám phá các khía cạnh chính, cung cấp một số thông tin hữu ích và "
            "giúp bạn hiểu tại sao đây là xu hướng đáng chú ý.\n\n"
            "## Tổng quan\n\n"
            "Có nhiều yếu tố cần cân nhắc. Doanh nghiệp nên tận dụng các giải pháp phù hợp để tối ưu hiệu quả.\n\n"
            "## Kết luận\n\n"
            "Tóm lại, đây là một chủ đề quan trọng và cần được quan tâm trong tương lai."
        )

    def _score_content_against_profile(
        self,
        content: str,
        profile: dict[str, Any],
        channel: str,
        persona_name: str | None = None,
        include_breakdown: bool = False,
    ) -> Any:
        vocabulary = profile.get("vocabulary", {})
        style_rules = profile.get("style_rules", {})
        channel_guidelines = profile.get("channel_guidelines", {}).get(channel, {})
        brand_identity = profile.get("brand_identity", {})
        persona = self._select_persona(profile.get("audience_personas", []), persona_name)
        writing_fingerprint = profile.get("writing_fingerprint", {})
        forbidden_terms = list(vocabulary.get("forbidden_terms", []))
        forbidden_terms.extend(profile.get("dictionary", {}).get("forbidden_replacements", {}).keys())
        preferred_terms = [
            term for term in vocabulary.get("preferred_phrases", []) + vocabulary.get("repeated_terms", [])
            if isinstance(term, str) and len(term) > 2
        ][:40]
        identity_terms = self._dedupe_strings(
            brand_identity.get("personality_traits", [])
            + brand_identity.get("differentiators", [])
            + [brand_identity.get("positioning", ""), brand_identity.get("value_proposition", "")]
        )[:20]

        lowered = content.lower()
        violations = []
        recommendations = []

        forbidden_hits = sorted({term for term in forbidden_terms if term and term.lower() in lowered})
        if forbidden_hits:
            violations.append(f"Forbidden/off-brand terms found: {', '.join(forbidden_hits)}")

        preferred_hits = sorted({term for term in preferred_terms if term.lower() in lowered})
        vocabulary_score = min(100, 55 + len(preferred_hits) * 7) - len(forbidden_hits) * 20
        if preferred_terms and len(preferred_hits) < min(3, len(preferred_terms)):
            recommendations.append("Add more preferred brand vocabulary from the profile.")

        sentences = [s.strip() for s in re.split(r"(?<=[.!?。！？])\s+", content) if s.strip()]
        sentence_lengths = [len(re.findall(r"\S+", sentence)) for sentence in sentences]
        avg_sentence_words = sum(sentence_lengths) / max(1, len(sentence_lengths))
        max_sentence_words = int(style_rules.get("max_sentence_words", 28))
        readability_score = 100 if avg_sentence_words <= max_sentence_words else max(35, 100 - int((avg_sentence_words - max_sentence_words) * 4))
        if avg_sentence_words > max_sentence_words:
            violations.append(
                f"Average sentence length is {avg_sentence_words:.1f} words; target is <= {max_sentence_words}."
            )

        has_h1 = bool(re.search(r"^#\s+", content, re.MULTILINE))
        has_h2 = bool(re.search(r"^##\s+", content, re.MULTILINE))
        structure_score = 100
        if channel == "blog" and not has_h1:
            structure_score -= 25
            recommendations.append("Start blog drafts with an H1 title.")
        if channel == "blog" and not has_h2:
            structure_score -= 25
            recommendations.append("Use H2 sections to match the blog presentation profile.")

        generic_phrases = [
            "trong thời đại số",
            "ngày càng trở nên quan trọng",
            "xu hướng đáng chú ý",
            "tối ưu hiệu quả",
            "khám phá các khía cạnh",
        ]
        generic_hits = [phrase for phrase in generic_phrases if phrase in lowered]
        tone_score = max(35, 100 - len(generic_hits) * 12)
        if generic_hits:
            violations.append(f"Generic AI-sounding phrases found: {', '.join(generic_hits)}")

        channel_score = 85
        for rule in channel_guidelines.get("rules", []):
            if "clear h2" in rule.lower() and has_h2:
                channel_score += 5
            if "avoid unsupported hype" in rule.lower() and not generic_hits:
                channel_score += 5
        channel_score = min(100, channel_score)

        identity_hits = sorted({term for term in identity_terms if term and term.lower() in lowered})
        identity_score = 85 if not identity_terms else min(100, 60 + len(identity_hits) * 8)
        if identity_terms and not identity_hits:
            recommendations.append("Reflect the configured brand identity more explicitly.")

        persona_score = 85
        if persona:
            persona_text = json.dumps(
                {
                    "name": persona.get("name", ""),
                    "priorities": persona.get("priorities", []),
                    "decision_criteria": persona.get("decision_criteria", []),
                    "tone_adjustment": persona.get("tone_adjustment", ""),
                },
                ensure_ascii=False,
            )
            persona_terms = self._persona_match_tokens(persona_text)
            persona_hits = persona_terms & self._persona_match_tokens(content)
            persona_score = 90 if not persona_terms else min(100, 60 + len(persona_hits) * 5)
            if persona_terms and len(persona_hits) < 4:
                recommendations.append(f"Adapt the piece more clearly for persona: {persona.get('name')}.")

        fingerprint_result = self._score_writing_fingerprint(
            content,
            writing_fingerprint,
            include_breakdown=include_breakdown,
        )
        if include_breakdown:
            (
                fingerprint_score,
                fingerprint_violations,
                fingerprint_recommendations,
                fingerprint_breakdown,
            ) = fingerprint_result
        else:
            fingerprint_score, fingerprint_violations, fingerprint_recommendations = fingerprint_result
            fingerprint_breakdown = []
        violations.extend(fingerprint_violations)
        recommendations.extend(fingerprint_recommendations)

        if not violations:
            recommendations.append("Save this as a potential gold-standard output if human review agrees.")
        else:
            recommendations.append("Update the profile or add better examples if these violations recur.")

        scores = {
            "tone_alignment": max(0, min(100, tone_score)),
            "vocabulary": max(0, min(100, vocabulary_score)),
            "readability": max(0, min(100, readability_score)),
            "structure": max(0, min(100, structure_score)),
            "channel_fit": max(0, min(100, channel_score)),
            "identity_alignment": max(0, min(100, identity_score)),
            "persona_fit": max(0, min(100, persona_score)),
            "writing_fingerprint_fit": max(0, min(100, fingerprint_score)),
        }
        if include_breakdown:
            return scores, violations, recommendations, {"fingerprint": fingerprint_breakdown}
        return scores, violations, recommendations

    def _score_writing_fingerprint(
        self,
        content: str,
        writing_fingerprint: dict[str, Any],
        include_breakdown: bool = False,
    ) -> Any:
        if not writing_fingerprint:
            result = (85, [], [])
            if include_breakdown:
                return *result, [{
                    "criterion": "Dữ liệu writing fingerprint",
                    "score": 85,
                    "reason": "Profile chưa có đủ dữ liệu fingerprint để đối chiếu chi tiết.",
                    "suggestion": "Bổ sung thêm writing samples đã được duyệt rồi train lại profile.",
                }]
            return result

        target_patterns = writing_fingerprint.get("sentence_patterns", {})
        target_vocab = writing_fingerprint.get("vocabulary_fingerprints", {})
        target_perspective = writing_fingerprint.get("perspective_matching", {})
        content_metrics = self._text_style_metrics(content)
        content_perspective = self._infer_perspective(content)
        lowered = content.lower()

        score = 100
        violations = []
        recommendations = []
        breakdown: list[dict[str, Any]] = []

        def deduct(criterion: str, points: int, reason: str, suggestion: str) -> None:
            nonlocal score
            points = max(0, int(points))
            if points == 0:
                return
            score -= points
            breakdown.append(
                {
                    "criterion": criterion,
                    "score": max(0, 100 - points),
                    "reason": reason,
                    "suggestion": suggestion,
                }
            )

        target_avg = float(target_patterns.get("average_sentence_words") or 0)
        if target_avg > 0:
            avg_diff = abs(float(content_metrics["average_sentence_words"]) - target_avg)
            tolerance = max(3.0, target_avg * 0.25)
            deduct(
                "Độ dài câu",
                min(15, round(max(0.0, avg_diff - tolerance) * 1.5)),
                f"Độ dài câu trung bình lệch {avg_diff:.1f} từ so với fingerprint mẫu.",
                "Điều chỉnh độ dài câu gần hơn với nhịp câu đã học từ writing samples.",
            )
            if avg_diff > 8:
                recommendations.append("Adjust sentence length closer to the learned writing fingerprint.")

        for key, label, criterion in [
            ("short_fragment_ratio", "short fragment rhythm", "Nhịp câu ngắn"),
            ("rhetorical_question_ratio", "rhetorical question rhythm", "Câu hỏi tu từ"),
            ("parenthetical_aside_ratio", "parenthetical aside rhythm", "Nhịp câu trong ngoặc"),
        ]:
            target_value = float(target_patterns.get(key) or 0)
            actual_value = float(content_metrics.get(key) or 0)
            diff = abs(actual_value - target_value)
            deduct(
                criterion,
                min(8, round(diff * 40)),
                f"Tỷ lệ thực tế {actual_value:.3f} khác mức mẫu {target_value:.3f}.",
                f"Điều chỉnh {label} gần hơn với writing samples.",
            )
            if target_value >= 0.05 and actual_value < target_value / 2:
                recommendations.append(f"Use more {label} to match the source style.")

        target_dash = float(target_patterns.get("dash_usage_per_1000_words") or 0)
        actual_dash = float(content_metrics.get("dash_usage_per_1000_words") or 0)
        dash_diff = abs(actual_dash - target_dash)
        deduct(
            "Mật độ dấu gạch ngang",
            min(6, round(dash_diff)),
            f"Mật độ dấu gạch ngang lệch {dash_diff:.1f} lần trên 1.000 từ.",
            "Điều chỉnh cách dùng dấu gạch ngang theo nhịp văn mẫu.",
        )

        target_active = float(target_patterns.get("active_voice_ratio") or 0)
        actual_active = float(content_metrics.get("active_voice_ratio") or 0)
        if target_active and actual_active + 0.15 < target_active:
            deduct(
                "Tỷ lệ câu chủ động",
                10,
                f"Tỷ lệ câu chủ động {actual_active:.2f} thấp hơn mức mẫu {target_active:.2f}.",
                "Ưu tiên cấu trúc câu chủ động để sát fingerprint hơn.",
            )
            recommendations.append("Prefer active voice to match the learned sentence pattern.")

        transition_phrases = [
            phrase for phrase in target_vocab.get("transition_phrases", [])
            if isinstance(phrase, str) and phrase.strip()
        ]
        if transition_phrases and not any(phrase.lower() in lowered for phrase in transition_phrases):
            deduct(
                "Cụm chuyển ý đặc trưng",
                8,
                "Bài viết chưa sử dụng cụm chuyển ý đã học từ writing samples.",
                "Dùng một cụm chuyển ý phù hợp với ngữ cảnh, tránh chèn máy móc.",
            )
            recommendations.append("Reuse learned transition phrases where they fit naturally.")

        forbidden_cliches = [
            phrase for phrase in target_vocab.get("forbidden_cliches", [])
            if isinstance(phrase, str) and phrase.strip()
        ]
        cliche_hits = sorted({phrase for phrase in forbidden_cliches if phrase.lower() in lowered})
        if cliche_hits:
            deduct(
                "Sáo ngữ bị cấm",
                min(30, len(cliche_hits) * 10),
                f"Phát hiện sáo ngữ: {', '.join(cliche_hits)}.",
                "Viết lại các cụm sáo ngữ bằng cách diễn đạt cụ thể và đúng brand voice.",
            )
            violations.append(f"Writing fingerprint cliches found: {', '.join(cliche_hits)}")

        for key, label in [
            ("self_reference", "self-reference"),
            ("reader_address", "reader address"),
            ("stance", "stance"),
        ]:
            expected = str(target_perspective.get(key) or "").strip()
            actual = str(content_perspective.get(key) or "").strip()
            if (
                expected
                and expected not in ("unspecified", "reader")
                and not self._perspective_matches(key, expected, actual)
            ):
                deduct(
                    {
                        "self_reference": "Cách thương hiệu tự xưng",
                        "reader_address": "Cách xưng hô với người đọc",
                        "stance": "Lập trường người viết",
                    }[key],
                    8,
                    f"Mẫu yêu cầu '{expected}' nhưng bài hiện thể hiện '{actual}'.",
                    f"Điều chỉnh {label} theo perspective đã học.",
                )
                recommendations.append(f"Match the learned {label}: expected '{expected}', saw '{actual}'.")

        result = (max(0, min(100, score)), violations, recommendations)
        return (*result, breakdown) if include_breakdown else result

    def _select_persona(
        self,
        personas: list[dict[str, Any]],
        persona_name: str | None,
    ) -> dict[str, Any] | None:
        if not personas:
            return None
        query = str(persona_name or "").strip()
        if not query:
            return personas[0]
        wanted = query.casefold()
        exact = next(
            (persona for persona in personas if str(persona.get("name", "")).casefold() == wanted),
            None,
        )
        if exact is not None:
            return exact

        query_tokens = self._persona_match_tokens(query)
        ranked = []
        for index, persona in enumerate(personas):
            persona_tokens = self._persona_match_tokens(
                json.dumps(persona, ensure_ascii=False)
            )
            overlap = query_tokens & persona_tokens
            score = sum(
                6 if token in {"singing", "business"} else 3 if token == "hoanh" else 1
                for token in overlap
            )
            ranked.append((score, -index, persona))
        best = max(ranked, key=lambda item: (item[0], item[1]))
        return best[2] if best[0] > 0 else personas[0]

    @classmethod
    def _perspective_matches(cls, key: str, expected: str, actual: str) -> bool:
        expected_tokens = cls._persona_match_tokens(expected)
        actual_tokens = cls._persona_match_tokens(actual)
        if not actual_tokens:
            return False
        if actual_tokens <= expected_tokens:
            return True
        if key == "stance" and actual.casefold() == "mentor":
            mentor_markers = {
                "chuyen gia", "dan duong", "huong dan", "su pham", "co van", "advisor"
            }
            plain_expected = unicodedata.normalize("NFD", expected.casefold())
            plain_expected = "".join(
                char for char in plain_expected if unicodedata.category(char) != "Mn"
            )
            return any(marker in plain_expected for marker in mentor_markers)
        return False

    @staticmethod
    def _persona_match_tokens(value: str) -> set[str]:
        normalized = unicodedata.normalize("NFD", value.casefold())
        normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
        tokens = set(re.findall(r"[a-z0-9]+", normalized))
        stopwords = {
            "va", "voi", "cho", "cua", "cac", "mot", "nhung", "trong", "tu",
            "den", "theo", "duoc", "nguoi", "nha", "su", "ve", "khi", "de",
            "and", "the", "for", "with", "from", "that", "this",
        }
        aliases = {
            "hat": "singing", "thanh": "singing", "nhac": "singing",
            "ca": "singing", "si": "singing",
            "doanh": "business", "nhan": "business", "quan": "business",
            "ly": "business", "dam": "business", "phan": "business",
        }
        return {aliases.get(token, token) for token in tokens if token not in stopwords}

    @staticmethod
    def _dedupe_strings(values: list[Any]) -> list[str]:
        seen = set()
        output = []
        for value in values:
            text = str(value).strip()
            key = text.lower()
            if text and key not in seen:
                seen.add(key)
                output.append(text)
        return output

    def _judge_with_llm(
        self,
        content: str,
        profile: dict[str, Any],
        channel: str,
        persona_name: str | None,
    ) -> dict[str, Any] | None:
        prompt = self._build_judge_prompt(content, profile, channel, persona_name)
        try:
            llm = LLMFactory(self._settings).create(self._settings.EDITOR_MODEL)
            response = llm.call([{"role": "user", "content": prompt}])
            data = self._parse_json(response)
            scores = data.get("dimension_scores", {})
            if not isinstance(scores, dict):
                scores = {}
            overall = int(data.get("overall_score") or 0)
            if overall <= 0 and scores:
                overall = round(sum(int(v) for v in scores.values()) / max(1, len(scores)))
            data["overall_score"] = max(0, min(100, overall))
            data["dimension_scores"] = {
                str(key): max(0, min(100, int(value)))
                for key, value in scores.items()
                if str(value).isdigit() or isinstance(value, int)
            }
            data["violations"] = data.get("violations", [])
            data["recommendations"] = data.get("recommendations", [])
            return data
        except Exception as e:
            logger.warning("Brand voice LLM judge failed; using heuristic only | {}", e)
            return None

    def _build_judge_prompt(
        self,
        content: str,
        profile: dict[str, Any],
        channel: str,
        persona_name: str | None,
    ) -> str:
        profile_summary = {
            "brand_identity": profile.get("brand_identity", {}),
            "audience_personas": profile.get("audience_personas", []),
            "tone": profile.get("tone", {}),
            "vocabulary": profile.get("vocabulary", {}),
            "syntax": profile.get("syntax", {}),
            "presentation": profile.get("presentation", {}),
            "writing_fingerprint": profile.get("writing_fingerprint", {}),
            "rubrics": profile.get("rubrics", []),
            "channel_guidelines": profile.get("channel_guidelines", {}).get(channel, {}),
        }
        return (
            "You are a strict brand voice evaluator. Score the content against the profile.\n"
            f"Channel: {channel}\n"
            f"Persona: {persona_name or 'default'}\n\n"
            "Return only valid JSON with this schema:\n"
            "{\n"
            '  "overall_score": 0,\n'
            '  "dimension_scores": {"identity_alignment": 0, "persona_fit": 0, "tone_alignment": 0, "vocabulary": 0, "structure": 0, "writing_fingerprint_fit": 0},\n'
            '  "violations": [],\n'
            '  "recommendations": [],\n'
            '  "rationale": ""\n'
            "}\n\n"
            f"Brand Voice Profile:\n{json.dumps(profile_summary, ensure_ascii=False)[:6000]}\n\n"
            f"Content to evaluate:\n{content[:8000]}"
        )

    def _index_profile(self, profile_markdown: str, profile: dict[str, Any]) -> int:
        try:
            self._store.delete_document(PROFILE_DOCUMENT_ID)
            chunks = [profile_markdown[i:i + 1800] for i in range(0, len(profile_markdown), 1800)]
            metadatas = [
                {
                    "document_id": PROFILE_DOCUMENT_ID,
                    "filename": "brand_voice_profile.md",
                    "chunk_index": index,
                    "content_type": "brand_voice_profile",
                    "profile_id": profile["profile_id"],
                }
                for index, _ in enumerate(chunks)
            ]
            ids = [f"{PROFILE_DOCUMENT_ID}_{index}" for index, _ in enumerate(chunks)]
            self._store.add_documents(chunks, metadatas, ids)
            profile["indexed_chunks"] = len(chunks)
            self._write_profile(profile)
            return len(chunks)
        except Exception as e:
            raise ToolExecutionError(
                f"Cannot index brand voice profile: {e}",
                {"profile_id": profile.get("profile_id")},
            ) from e
