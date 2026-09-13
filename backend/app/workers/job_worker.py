from __future__ import annotations

import inspect
import re
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.logging import logger
from app.repositories.brand_voice_profile_repository import BrandVoiceProfileRepository
from app.repositories.generation_repository import GenerationRunRepository
from app.repositories.job_repository import JobRepository
from app.services.quality_gate import QualityGate


class WorkflowJobHandlers:
    def __init__(
        self,
        content_service: Any,
        runs: GenerationRunRepository,
        profiles: BrandVoiceProfileRepository,
        *,
        quality_gate: QualityGate | None = None,
        profile_trainer: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]] | None = None,
        brand_voice_service: Any | None = None,
        final_evaluator: Any | None = None,
        seo_evaluator: Any | None = None,
        seo_research_enabled: bool = False,
        existing_blogs_provider: Callable[[str], list[dict[str, Any]]] | None = None,
    ):
        self.content_service = content_service
        self.runs = runs
        self.profiles = profiles
        self.quality_gate = quality_gate or QualityGate()
        self.profile_trainer = profile_trainer
        self.brand_voice_service = brand_voice_service
        self.final_evaluator = final_evaluator
        self.seo_evaluator = seo_evaluator
        self.seo_research_enabled = seo_research_enabled
        self.existing_blogs_provider = existing_blogs_provider

    async def handle(self, job: dict[str, Any]) -> dict[str, Any]:
        if job["job_type"] == "plan":
            return await self._plan(job)
        if job["job_type"] == "generate":
            try:
                return await self._generate(job)
            except Exception:
                self.runs.fail_generation(job["payload"]["run_id"])
                raise
        if job["job_type"] == "train_profile" and self.profile_trainer:
            return await self.profile_trainer(job["project_id"], job["payload"])
        raise ValueError(f"Unsupported job type: {job['job_type']}")

    async def _plan(self, job: dict[str, Any]) -> dict[str, Any]:
        run = self._required_run(job["payload"]["run_id"])
        brief = run["brief"]
        result = await self.content_service.generate_titles(
            brief["keywords"],
            use_web_search=(
                brief.get("use_web_search", False)
                or brief.get("seo_research_enabled", False)
                or self.seo_research_enabled
            ),
            project_id=run["project_id"],
            seo_context=(
                f"Primary keyword: {brief.get('primary_keyword') or brief['keywords'][0]}\n"
                f"Search intent: {brief.get('search_intent', 'auto')}\n"
                f"Topic: {brief.get('topic', '')}\n"
                f"Audience: {brief.get('audience', '')}\n"
                f"Objective: {brief.get('objective', '')}"
            ),
        )
        plans = result.get("titles") or []
        if not plans:
            raise ValueError("Planner returned no outline")
        plan = plans[0]
        updated = self.runs.set_plan(
            run["run_id"],
            plan["title"],
            plan.get("seo_title") or plan["title"],
            plan.get("outline") or [],
            seo_research=result.get("seo_research"),
        )
        return {"run_id": run["run_id"], "status": updated["status"]}

    async def _generate(self, job: dict[str, Any]) -> dict[str, Any]:
        run = self._required_run(job["payload"]["run_id"])
        self.runs.begin_generation(run["run_id"])
        run = self._required_run(run["run_id"])
        brief = run["brief"]
        planner_research = (run.get("quality_report") or {}).get("seo_research") or {}
        use_web_search = bool(
            brief.get("use_web_search", False)
            or brief.get("seo_research_enabled", False)
            or self.seo_research_enabled
        )
        result = await self.content_service.generate_content(
            keywords=brief["keywords"],
            selected_title=run["planned_title"] or brief["topic"],
            outline=run["outline"],
            use_web_search=use_web_search,
            project_id=run["project_id"],
            profile_id=run["profile_id"],
            brief_context=(
                f"Audience: {brief.get('audience', '')}\n"
                f"Objective: {brief.get('objective', '')}\n"
                f"Category: {brief.get('category') or ''}\n"
                f"Target length: {brief.get('target_length', 800)} words\n"
                f"Must cover: {', '.join(brief.get('must_cover') or [])}\n"
                f"Must avoid: {', '.join(brief.get('must_avoid') or [])}"
                f"\nPrimary keyword: {brief.get('primary_keyword') or brief['keywords'][0]}"
                f"\nSearch intent: {brief.get('search_intent', 'auto')}"
            ),
        )
        content = result["optimized_content"]
        seo_package = {
            "seo_title": result.get("seo_title") or result.get("title_tag") or run.get("planned_seo_title"),
            "meta_description": result.get("meta_description"),
            "suggested_slug": result.get("suggested_slug"),
        }
        style_report = result.get("style_report") or {}
        citations = list(result.get("citations") or [])
        retrieved_contexts = list(result.get("retrieved_contexts") or [])
        seo_research = self._merge_research_reports(
            planner_research,
            result.get("seo_research") or {},
        )
        self.runs.replace_citations(run["run_id"], citations)
        self.runs.replace_retrieval_contexts(run["run_id"], retrieved_contexts)
        rewrite_count = 0

        while True:
            quality_report = self._evaluate(
                content,
                style_report,
                run,
                seo_title=seo_package.get("seo_title"),
                meta_description=seo_package.get("meta_description"),
                suggested_slug=seo_package.get("suggested_slug"),
            )
            quality_report["seo_research"] = seo_research
            terminal_attempt = quality_report["passed"] or rewrite_count >= 2
            if terminal_attempt and self.final_evaluator is not None:
                stored = (
                    self.profiles.get(run["project_id"], run["profile_id"])
                    if run.get("profile_id")
                    else None
                )
                final_evaluation = self.final_evaluator.evaluate(
                    content=content,
                    brief=brief,
                    quality_report=quality_report,
                    profile=stored["profile"] if stored else None,
                )
                quality_report["final_evaluation"] = final_evaluation
            self.runs.record_attempt(
                run["run_id"], content, quality_report, self._model_name(), duration_seconds=None
            )
            if terminal_attempt:
                break
            rewritten = await self.content_service.rewrite_content(
                content,
                self._quality_feedback(quality_report["violations"]),
                project_id=run["project_id"],
                profile_id=run["profile_id"],
            )
            content = rewritten["rewritten_text"]
            build_package = getattr(self.content_service, "build_seo_package", None)
            if callable(build_package):
                seo_package = build_package(
                    content,
                    seo_title=str(
                        self._extract_h1(content)
                        or seo_package.get("seo_title")
                        or ""
                    ),
                    primary_keyword=str(
                        brief.get("primary_keyword") or brief["keywords"][0]
                    ),
                    search_intent=str(brief.get("search_intent", "auto")),
                )
            style_report = {
                **style_report,
                **(rewritten.get("style_report") or {}),
            }
            rewrite_count += 1

        finalized = self.runs.finalize(
            run["run_id"],
            content,
            quality_report,
            rewrite_count,
            self._extract_h1(content) or result.get("title_tag"),
            seo_package.get("meta_description"),
        )
        return {
            "run_id": run["run_id"],
            "status": finalized["status"],
            "passed": quality_report["passed"],
        }

    def _evaluate(
        self,
        content: str,
        style_report: dict[str, Any],
        run: dict[str, Any],
        *,
        seo_title: str | None = None,
        meta_description: str | None = None,
        suggested_slug: str | None = None,
    ) -> dict[str, Any]:
        provided = style_report.get("dimension_scores") or {}
        style_score = int(style_report.get("style_score", provided.get("style", 0)))
        profile_evaluation: dict[str, Any] = {}
        forbidden_terms = list(style_report.get("remaining_forbidden_terms") or [])
        stored = self.profiles.get(run["project_id"], run["profile_id"]) if run.get("profile_id") else None
        if self.brand_voice_service is not None and stored is not None:
            profile = stored["profile"]
            profile_evaluation = self.brand_voice_service.score_content_against_profile(
                content,
                profile,
                channel="blog",
                persona_name=str(run["brief"].get("audience") or ""),
            )
            profile_scores = profile_evaluation.get("dimension_scores") or {}
            brand_parts = [
                int(profile_scores[key])
                for key in ("tone_alignment", "vocabulary", "identity_alignment")
                if key in profile_scores
            ]
            style_parts = [
                style_score,
                *[
                    int(profile_scores[key])
                    for key in ("structure", "readability")
                    if key in profile_scores
                ],
            ]
            provided = {
                "brand": round(sum(brand_parts) / len(brand_parts)) if brand_parts else 0,
                "style": round(sum(style_parts) / len(style_parts)),
                "fingerprint": int(profile_scores.get("writing_fingerprint_fit", 0)),
                "persona": int(profile_scores.get("persona_fit", 0)),
            }
            dictionary = profile.get("dictionary", {})
            forbidden_terms.extend(dictionary.get("forbidden_replacements", {}).keys())
            forbidden_terms.extend(
                profile.get("writing_fingerprint", {})
                .get("vocabulary_fingerprints", {})
                .get("forbidden_cliches", [])
            )
        dimensions = {
            "brand": int(provided.get("brand", style_score)),
            "style": int(provided.get("style", style_score)),
            "fingerprint": int(provided.get("fingerprint", 0)),
            "persona": int(provided.get("persona", 0)),
        }
        profile_scores = profile_evaluation.get("dimension_scores") or {}
        score_breakdown = {
            "brand": [
                {"criterion": "Tone thương hiệu", "score": int(profile_scores.get("tone_alignment", dimensions["brand"]))},
                {"criterion": "Từ vựng thương hiệu", "score": int(profile_scores.get("vocabulary", dimensions["brand"]))},
                {"criterion": "Nhận diện thương hiệu", "score": int(profile_scores.get("identity_alignment", dimensions["brand"]))},
            ],
            "style": [
                {"criterion": "Quy tắc trình bày", "score": style_score},
                {"criterion": "Cấu trúc bài viết", "score": int(profile_scores.get("structure", dimensions["style"]))},
                {"criterion": "Độ dễ đọc", "score": int(profile_scores.get("readability", dimensions["style"]))},
            ],
            "fingerprint": [
                *(
                    (profile_evaluation.get("score_breakdown") or {}).get("fingerprint")
                    or [{"criterion": "Writing fingerprint", "score": int(profile_scores.get("writing_fingerprint_fit", dimensions["fingerprint"]))}]
                ),
            ],
            "persona": [
                {"criterion": "Mức độ phù hợp persona", "score": int(profile_scores.get("persona_fit", dimensions["persona"]))},
            ],
        }
        report = self.quality_gate.evaluate(
            content,
            dimension_scores=dimensions,
            forbidden_terms=sorted(set(str(item) for item in forbidden_terms if item)),
            project_leakage=bool(style_report.get("project_leakage", False)),
            must_cover=list(run["brief"].get("must_cover") or []),
            must_avoid=list(run["brief"].get("must_avoid") or []),
            target_length=int(run["brief"].get("target_length") or 0) or None,
        )
        report["profile_evaluation"] = profile_evaluation
        report["score_breakdown"] = score_breakdown
        if self.seo_evaluator is not None:
            seo_evaluation = self.seo_evaluator.evaluate(
                content=content,
                brief=run["brief"],
                seo_title=seo_title,
                meta_description=meta_description,
                suggested_slug=suggested_slug,
                existing_project_blogs=(
                    self.existing_blogs_provider(run["project_id"])
                    if self.existing_blogs_provider is not None
                    else []
                ),
            )
            seo_score = int(seo_evaluation["score"])
            report["dimension_scores"]["seo"] = seo_score
            report["seo_evaluation"] = seo_evaluation
            report["score_breakdown"]["seo"] = [
                {
                    "criterion": name.replace("_", " ").title(),
                    "score": int(value),
                }
                for name, value in seo_evaluation.get("subscores", {}).items()
            ]
            if seo_evaluation.get("gated") and seo_score < int(seo_evaluation["threshold"]):
                body_codes = {
                    "search_intent_satisfaction",
                    "helpful_completeness",
                    "information_gain_originality",
                    "evidence_expertise_trust",
                    "semantic_topic_coverage",
                    "keyword_usage",
                    "keyword_repetition",
                    "content_structure",
                }
                report["violations"].extend(
                    {"code": f"seo_{check['code']}", "recommendation": check.get("recommendation")}
                    for check in seo_evaluation.get("checks", [])
                    if check.get("status") == "needs_attention"
                    and check.get("code") in body_codes
                )
                report["violations"].append(
                    {
                        "code": "seo_below_threshold",
                        "actual": seo_score,
                        "threshold": int(seo_evaluation["threshold"]),
                    }
                )
                report["passed"] = False
        return report

    @staticmethod
    def _extract_h1(content: str) -> str | None:
        match = re.search(r"(?m)^#\s+(.+?)\s*$", content)
        return match.group(1).strip() if match else None

    @staticmethod
    def _merge_research_reports(*reports: dict[str, Any]) -> dict[str, list[Any]]:
        queries: list[str] = []
        sources: list[dict[str, Any]] = []
        urls: list[str] = []
        seen_sources: set[str] = set()
        for report in reports:
            for query in report.get("query_variations") or []:
                value = str(query).strip()
                if value and value not in queries:
                    queries.append(value)
            for source in report.get("sources") or []:
                if not isinstance(source, dict):
                    continue
                url = str(source.get("url") or "").strip()
                if not url or url in seen_sources:
                    continue
                sources.append(dict(source))
                seen_sources.add(url)
                urls.append(url)
            for source_url in report.get("source_urls") or []:
                url = str(source_url).strip()
                if url and url not in urls:
                    urls.append(url)
        return {"query_variations": queries, "sources": sources, "source_urls": urls}

    @staticmethod
    def _quality_feedback(violations: list[dict[str, Any]]) -> str:
        details = []
        for violation in violations:
            code = str(violation.get("code", "unknown"))
            if code == "target_length_mismatch":
                actual = violation.get("actual")
                minimum = violation.get("minimum")
                maximum = violation.get("maximum")
                direction = "shorten" if int(actual or 0) > int(maximum or 0) else "expand"
                details.append(
                    f"- target_length_mismatch (actual={actual}; minimum={minimum}; maximum={maximum}): "
                    f"{direction} the article from {actual} words "
                    f"to between {minimum} and {maximum} words. Remove repetition before "
                    "returning the complete article and do not add new sections."
                )
                continue
            values = [
                f"{key}={value}"
                for key, value in violation.items()
                if key != "code"
            ]
            details.append(f"- {code}" + (f" ({'; '.join(values)})" if values else ""))
        return (
            "Fix only the quality violations below while preserving factual meaning, citations, "
            "Markdown headings, and all compliant content. Return only the complete revised article.\n"
            + "\n".join(details)
        )

    def _required_run(self, run_id: str) -> dict[str, Any]:
        run = self.runs.get(run_id)
        if run is None:
            raise ValueError("Generation run not found")
        return run

    def _model_name(self) -> str:
        settings = getattr(self.content_service, "_settings", None)
        if (
            settings is not None
            and getattr(settings, "AI_PROVIDER", None) == "vllm"
        ):
            return str(getattr(settings, "VLLM_MODEL_NAME", "unknown"))
        return str(getattr(settings, "WRITER_MODEL", "unknown"))


class JobWorker:
    def __init__(
        self,
        repository: JobRepository,
        handler: Callable[[dict[str, Any]], Awaitable[dict[str, Any]] | dict[str, Any]],
    ):
        self.repository = repository
        self.handler = handler

    async def run_once(self) -> bool:
        job = self.repository.claim_next()
        if job is None:
            return False
        try:
            result = self.handler(job)
            if inspect.isawaitable(result):
                result = await result
            self.repository.complete(job["job_id"], result)
        except Exception as exc:
            logger.exception("Job failed | job_id={} type={}", job["job_id"], job["job_type"])
            self.repository.fail(job["job_id"], {"message": str(exc), "type": type(exc).__name__})
        return True
