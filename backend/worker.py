import asyncio

from app.api.v1.content_router import _get_content_service
from app.core.logging import logger, setup_logging
from app.repositories.brand_voice_profile_repository import BrandVoiceProfileRepository
from app.repositories.generation_repository import GenerationRunRepository
from app.repositories.job_repository import JobRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.blog_repository import BlogRepository
from app.db.database import get_connection
from app.api.v1.document_router import get_brand_voice_service
from app.workers.job_worker import JobWorker, WorkflowJobHandlers
from app.workers.profile_trainer import ProjectProfileTrainer
from app.core.config import get_settings
from app.services.final_evaluation_service import FinalEvaluationService
from app.services.seo_evaluation_service import SeoEvaluationService
from app.services.seo_judge_factory import create_seo_judge


def recover_interrupted_jobs(jobs: JobRepository, runs: GenerationRunRepository) -> int:
    for job in jobs.list_running():
        if job["job_type"] == "generate" and job["payload"].get("run_id"):
            runs.fail_generation(job["payload"]["run_id"])
    return jobs.recover_running()


def build_seo_llm(settings):
    if not settings.SEO_LLM_JUDGE_ENABLED:
        return None
    try:
        return create_seo_judge(settings)
    except Exception as exc:
        logger.warning(
            "SEO LLM judge initialization failed; deterministic SEO evaluation remains enabled | error={}",
            exc,
        )
        return None


async def main() -> None:
    setup_logging()
    jobs = JobRepository()
    runs = GenerationRunRepository()
    recovered = recover_interrupted_jobs(jobs, runs)
    if recovered:
        logger.warning("Recovered {} jobs left running by a previous worker", recovered)
    profiles = BrandVoiceProfileRepository()
    brand_voice_service = get_brand_voice_service()
    trainer = ProjectProfileTrainer(brand_voice_service, DocumentRepository(), profiles)
    settings = get_settings()
    seo_llm = build_seo_llm(settings)

    def existing_blogs(project_id: str):
        with get_connection(runs.db_path) as conn:
            return BlogRepository(conn).list_all(project_id)

    handlers = WorkflowJobHandlers(
        _get_content_service(),
        runs,
        profiles,
        profile_trainer=trainer,
        brand_voice_service=brand_voice_service,
        final_evaluator=FinalEvaluationService(settings),
        seo_evaluator=(
            SeoEvaluationService(
                gate_enabled=settings.SEO_GATE_ENABLED,
                threshold=settings.SEO_GATE_THRESHOLD,
                duplicate_title_check=settings.SEO_DUPLICATE_TITLE_CHECK,
                duplicate_meta_check=settings.SEO_DUPLICATE_META_CHECK,
                llm=seo_llm,
                llm_enabled=settings.SEO_LLM_JUDGE_ENABLED,
            )
            if settings.SEO_EVALUATION_ENABLED
            else None
        ),
        seo_research_enabled=settings.SEO_RESEARCH_ENABLED,
        existing_blogs_provider=existing_blogs,
    )
    worker = JobWorker(jobs, handlers.handle)
    logger.info("Internal workflow worker started")
    while True:
        worked = await worker.run_once()
        if not worked:
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
