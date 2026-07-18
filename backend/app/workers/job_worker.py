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
    ):
        self.content_service = content_service
        self.runs = runs
        self.profiles = profiles
        self.quality_gate = quality_gate or QualityGate()
        self.profile_trainer = profile_trainer
        self.brand_voice_service = brand_voice_service

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
        self.runs.replace_citations(run["run_id"], citations)
        style_report["grounding_coverage"] = 1.0 if citations else 0.0
        rewrite_count = 0

        while True:
            quality_report = self._evaluate(content, style_report, run)
            self.runs.record_attempt(
                run["run_id"], content, quality_report, self._model_name(), duration_seconds=None
            )
            if quality_report["passed"] or rewrite_count >= 2:
                break
            codes = [item["code"] for item in quality_report["violations"]]
            rewritten = await self.content_service.rewrite_content(
                content,
                "Fix only these quality violations while preserving factual meaning: "
                + ", ".join(codes),
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
                content, profile, channel="blog"
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
        report = self.quality_gate.evaluate(
            content,
            dimension_scores=dimensions,
            forbidden_terms=sorted(set(str(item) for item in forbidden_terms if item)),
            grounding_coverage=float(style_report.get("grounding_coverage", 1.0)),
            project_leakage=bool(style_report.get("project_leakage", False)),
            must_cover=list(run["brief"].get("must_cover") or []),
            must_avoid=list(run["brief"].get("must_avoid") or []),
            target_length=int(run["brief"].get("target_length") or 0) or None,
        )
        report["profile_evaluation"] = profile_evaluation
        return report

    def _required_run(self, run_id: str) -> dict[str, Any]:
        run = self.runs.get(run_id)
        if run is None:
            raise ValueError("Generation run not found")
        return run

    def _model_name(self) -> str:
        settings = getattr(self.content_service, "_settings", None)
        return str(getattr(settings, "WRITER_MODEL", "qwen3.5-2b"))


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
