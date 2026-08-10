from __future__ import annotations

import inspect
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
    ):
        self.content_service = content_service
        self.runs = runs
        self.profiles = profiles
        self.quality_gate = quality_gate or QualityGate()
        self.profile_trainer = profile_trainer
        self.brand_voice_service = brand_voice_service
        self.final_evaluator = final_evaluator

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
            use_web_search=brief.get("use_web_search", False),
            project_id=run["project_id"],
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
        )
        return {"run_id": run["run_id"], "status": updated["status"]}

    async def _generate(self, job: dict[str, Any]) -> dict[str, Any]:
        run = self._required_run(job["payload"]["run_id"])
        self.runs.begin_generation(run["run_id"])
        run = self._required_run(run["run_id"])
        brief = run["brief"]
        result = await self.content_service.generate_content(
            keywords=brief["keywords"],
            selected_title=run["planned_title"] or brief["topic"],
            outline=run["outline"],
            use_web_search=brief.get("use_web_search", False),
            project_id=run["project_id"],
            profile_id=run["profile_id"],
            brief_context=(
                f"Audience: {brief.get('audience', '')}\n"
                f"Objective: {brief.get('objective', '')}\n"
                f"Category: {brief.get('category') or ''}\n"
                f"Target length: {brief.get('target_length', 800)} words\n"
                f"Must cover: {', '.join(brief.get('must_cover') or [])}\n"
                f"Must avoid: {', '.join(brief.get('must_avoid') or [])}"
            ),
        )
        content = result["optimized_content"]
        style_report = result.get("style_report") or {}
        citations = list(result.get("citations") or [])
        retrieved_contexts = list(result.get("retrieved_contexts") or [])
        self.runs.replace_citations(run["run_id"], citations)
        self.runs.replace_retrieval_contexts(run["run_id"], retrieved_contexts)
        rewrite_count = 0

        while True:
            quality_report = self._evaluate(content, style_report, run)
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
            result.get("title_tag"),
            result.get("meta_description"),
        )
        return {
            "run_id": run["run_id"],
            "status": finalized["status"],
            "passed": quality_report["passed"],
        }

    def _evaluate(
        self, content: str, style_report: dict[str, Any], run: dict[str, Any]
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
        return report

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
