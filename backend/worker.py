import asyncio

from app.api.v1.content_router import _get_content_service
from app.core.logging import logger, setup_logging
from app.repositories.brand_voice_profile_repository import BrandVoiceProfileRepository
from app.repositories.generation_repository import GenerationRunRepository
from app.repositories.job_repository import JobRepository
from app.repositories.document_repository import DocumentRepository
from app.api.v1.document_router import get_brand_voice_service
from app.workers.job_worker import JobWorker, WorkflowJobHandlers
from app.workers.profile_trainer import ProjectProfileTrainer
from app.core.config import get_settings
from app.services.final_evaluation_service import FinalEvaluationService


def recover_interrupted_jobs(jobs: JobRepository, runs: GenerationRunRepository) -> int:
    for job in jobs.list_running():
        if job["job_type"] == "generate" and job["payload"].get("run_id"):
            runs.fail_generation(job["payload"]["run_id"])
    return jobs.recover_running()


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
    handlers = WorkflowJobHandlers(
        _get_content_service(),
        runs,
        profiles,
        profile_trainer=trainer,
        brand_voice_service=brand_voice_service,
        final_evaluator=FinalEvaluationService(get_settings()),
    )
    worker = JobWorker(jobs, handlers.handle)
    logger.info("Internal workflow worker started")
    while True:
        worked = await worker.run_once()
        if not worked:
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
