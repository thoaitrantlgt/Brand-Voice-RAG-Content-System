"""Brand voice extraction and profile indexing service."""
from __future__ import annotations

import json
import re
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
        )
        overall = round(sum(scores.values()) / max(1, len(scores)))

        return BrandVoiceEvaluateResponse(
            profile_id=profile.get("profile_id", PROFILE_DOCUMENT_ID),
            channel=request.channel,
            content_type=request.content_type,
            overall_score=overall,
            dimension_scores=scores,
            violations=violations,
            recommendations=recommendations,
            reviewer_checklist=profile.get("governance", {}).get("reviewer_checklist", []),
        )

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
            '  "tone": {"primary": "", "secondary": [], "description": ""},\n'
            '  "vocabulary": {"repeated_terms": [], "preferred_phrases": [], "forbidden_terms": [], "replacements": {}},\n'
            '  "syntax": {"sentence_style": "", "average_sentence_words": 0, "rules": []},\n'
            '  "presentation": {"heading_style": "", "list_style": "", "chart_intro_style": "", "rules": []},\n'
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
        return {
            "profile_id": profile_id,
            "version": "2.0",
            "company_name": company_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_document_count": source_count,
            "source_documents": [
                {"document_id": doc["document_id"], "filename": doc["filename"]}
                for doc in documents
            ],
            "strategic_context": {
                "target_audience": request.target_audience or "Primary blog readers and prospective customers.",
                "brand_values": request.brand_values,
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
            },
        }

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

        lines = [
            f"# Brand Voice Profile: {profile.get('company_name', 'Company X')}",
            "",
            f"Version: {profile.get('version', '1.0')}",
            f"Profile ID: {profile.get('profile_id', PROFILE_DOCUMENT_ID)}",
            f"Source documents: {profile.get('source_document_count', 0)}",
            f"Recommended method: {profile.get('training_method_recommendation', {}).get('recommended_method', 'unknown')}",
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
            "## Channel Guidelines",
            json.dumps(profile.get("channel_guidelines", {}), ensure_ascii=False, indent=2),
            "",
            "## Calibration Tests",
        ]
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
    ) -> tuple[dict[str, int], list[str], list[str]]:
        vocabulary = profile.get("vocabulary", {})
        style_rules = profile.get("style_rules", {})
        channel_guidelines = profile.get("channel_guidelines", {}).get(channel, {})
        forbidden_terms = list(vocabulary.get("forbidden_terms", []))
        forbidden_terms.extend(profile.get("dictionary", {}).get("forbidden_replacements", {}).keys())
        preferred_terms = [
            term for term in vocabulary.get("preferred_phrases", []) + vocabulary.get("repeated_terms", [])
            if isinstance(term, str) and len(term) > 2
        ][:40]

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
        }
        return scores, violations, recommendations

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
