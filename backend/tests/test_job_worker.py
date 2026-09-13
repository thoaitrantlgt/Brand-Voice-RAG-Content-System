import pytest
import json
from pathlib import Path
from types import SimpleNamespace

from app.db.database import init_db
from app.repositories.brand_voice_profile_repository import BrandVoiceProfileRepository
from app.repositories.generation_repository import GenerationRunRepository
from app.repositories.job_repository import JobRepository
from app.workers.job_worker import JobWorker, WorkflowJobHandlers
from app.services.seo_evaluation_service import SeoEvaluationService
from app.workers.profile_trainer import ProjectProfileTrainer
from worker import build_seo_llm, recover_interrupted_jobs


class FakeContentService:
    def __init__(self):
        self.last_generate_kwargs = None

    async def generate_titles(self, keywords, use_web_search=False, project_id="default", seo_context=""):
        return {
            "titles": [
                {
                    "title": "Safe breath support",
                    "seo_title": "Safe breath support guide",
                    "outline": ["## Why it matters", "## Practice"],
                }
            ],
            "seo_research": {
                "query_variations": ["breath support basics"],
                "sources": [
                    {
                        "query": "breath support basics",
                        "title": "Planner source",
                        "url": "https://example.com/planner-source",
                        "snippet": "Planning evidence",
                        "domain": "example.com",
                    }
                ],
                "source_urls": ["https://example.com/planner-source"],
            },
        }

    async def generate_content(self, **kwargs):
        self.last_generate_kwargs = kwargs
        return {
            "optimized_content": "# Safe breath support\n\n## Why it matters\n\nClear body.",
            "title_tag": "Safe breath support",
            "seo_title": "Safe breath support",
            "meta_description": "A practical guide.",
            "style_report": {
                "style_score": 95,
                "remaining_forbidden_terms": [],
            },
            "citations": [
                {
                    "document_id": "doc-k1",
                    "chunk_index": 0,
                    "source_url": "https://example.com/source",
                    "excerpt": "Breath support source",
                    "relevance_score": 0.9,
                }
            ],
            "retrieved_contexts": [
                {
                    "document_id": "doc-k1",
                    "chunk_index": 0,
                    "text": "Full retrieved context about safe breath support.",
                    "relevance_score": 0.9,
                }
            ],
            "seo_research": {
                "query_variations": ["safe breath support"],
                "sources": [{"url": "https://example.com/source", "title": "Source", "snippet": "Evidence", "domain": "example.com", "query": "safe breath support"}],
                "source_urls": ["https://example.com/source"],
            },
        }


class FakeBrandVoiceService:
    def score_content_against_profile(self, content, profile, channel="blog", persona_name=None):
        return {
            "dimension_scores": {
                "tone_alignment": 90,
                "vocabulary": 88,
                "identity_alignment": 86,
                "structure": 92,
                "readability": 90,
                "writing_fingerprint_fit": 70,
                "persona_fit": 80,
            },
            "violations": [],
            "recommendations": [],
        }


class FakeFinalEvaluator:
    def evaluate(self, **kwargs):
        return {
            "status": "evaluated",
            "summary": "Final explanation",
            "dimensions": [],
            "annotations": [],
            "content_seen": kwargs["content"],
        }


def test_quality_feedback_includes_actionable_violation_details():
    feedback = WorkflowJobHandlers._quality_feedback(
        [
            {"code": "forbidden_term", "terms": ["Thư giãn"]},
            {"code": "target_length_mismatch", "actual": 430, "minimum": 480, "maximum": 1120},
        ]
    )

    assert "forbidden_term" in feedback
    assert "Thư giãn" in feedback
    assert "actual=430" in feedback
    assert "minimum=480" in feedback


@pytest.mark.asyncio
async def test_worker_processes_plan_and_generation_jobs(tmp_path):
    db_path = tmp_path / "worker.db"
    init_db(db_path)
    profiles = BrandVoiceProfileRepository(db_path)
    profile = profiles.create("alpha", "Main", {"tone": "direct"}, ["doc-1"])
    profiles.activate("alpha", profile["profile_id"])
    runs = GenerationRunRepository(db_path)
    jobs = JobRepository(db_path)
    run = runs.create(
        "alpha",
        {
            "topic": "Breath support",
            "keywords": ["support"],
            "audience": "students",
            "objective": "teach",
            "use_web_search": False,
            "seo_research_enabled": True,
        },
        "An",
        profile["profile_id"],
        profile["version"],
    )
    plan_job = jobs.enqueue(
        "alpha", "plan", {"run_id": run["run_id"]}, "An", idempotency_key="plan:run"
    )
    content_service = FakeContentService()
    handlers = WorkflowJobHandlers(
        content_service,
        runs,
        profiles,
        brand_voice_service=FakeBrandVoiceService(),
        final_evaluator=FakeFinalEvaluator(),
        seo_evaluator=SeoEvaluationService(),
    )
    worker = JobWorker(jobs, handlers.handle)

    assert await worker.run_once() is True
    planned = runs.get(run["run_id"])
    assert jobs.get(plan_job["job_id"])["status"] == "succeeded"
    assert planned["status"] == "outline_ready"
    assert planned["planned_title"] == "Safe breath support"
    assert planned["quality_report"]["seo_research"]["source_urls"] == [
        "https://example.com/planner-source"
    ]

    generation_job = jobs.enqueue(
        "alpha",
        "generate",
        {"run_id": run["run_id"]},
        "An",
        idempotency_key="generate:run",
    )
    assert await worker.run_once() is True
    generated = runs.get(run["run_id"])
    assert jobs.get(generation_job["job_id"])["status"] == "succeeded"
    assert generated["status"] == "needs_review"
    assert generated["quality_report"]["passed"] is True
    assert generated["rewrite_count"] == 0
    assert generated["quality_report"]["final_evaluation"]["summary"] == "Final explanation"
    assert generated["quality_report"]["score_breakdown"]["brand"] == [
        {"criterion": "Tone thương hiệu", "score": 90},
        {"criterion": "Từ vựng thương hiệu", "score": 88},
        {"criterion": "Nhận diện thương hiệu", "score": 86},
    ]
    assert "grounding_coverage" not in generated["quality_report"]
    assert "grounding_status" not in generated["quality_report"]
    assert generated["quality_report"]["dimension_scores"]["seo"] >= 0
    assert generated["quality_report"]["seo_evaluation"]["gated"] is False
    assert generated["quality_report"]["seo_evaluation"]["seo_package"]["seo_title"] == "Safe breath support"
    assert content_service.last_generate_kwargs["use_web_search"] is True
    assert generated["quality_report"]["seo_research"]["source_urls"] == [
        "https://example.com/planner-source",
        "https://example.com/source",
    ]
    assert generated["citations"][0]["document_id"] == "doc-k1"
    assert generated["retrieval_contexts"][0]["text"].startswith("Full retrieved")


def test_optional_seo_judge_init_failure_does_not_stop_worker(monkeypatch):
    from app.core.config import Settings

    def broken_factory(settings):
        raise ValueError("judge base URL is missing")

    monkeypatch.setattr("worker.create_seo_judge", broken_factory)

    assert build_seo_llm(Settings(SEO_LLM_JUDGE_ENABLED=True)) is None


@pytest.mark.asyncio
async def test_profile_training_job_only_uses_approved_project_documents(tmp_path):
    db_path = tmp_path / "trainer.db"
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps({"company_name": "Alpha", "tone": {"primary": "direct"}}))
    init_db(db_path)

    class Documents:
        def list(self, project_id=None, cluster=None):
            assert project_id == "alpha"
            assert cluster == "brand_voice"
            return [
                {"document_id": "approved", "approval_status": "approved", "human_rating": 5},
                {"document_id": "pending", "approval_status": "pending", "human_rating": None},
            ]

    class BrandService:
        async def train(self, request):
            assert request.document_ids == ["approved"]
            return SimpleNamespace(profile_path=str(profile_path), profile_markdown="profile")

    profiles = BrandVoiceProfileRepository(db_path)
    trainer = ProjectProfileTrainer(BrandService(), Documents(), profiles)
    result = await trainer(
        "alpha", {"name": "Main", "min_documents": 1, "max_documents": 30, "document_ids": []}
    )

    assert result["status"] == "active"
    assert profiles.get_active("alpha")["source_document_ids"] == ["approved"]
    first_artifact = result["artifact_path"]
    profile_path.write_text(json.dumps({"company_name": "Alpha", "tone": {"primary": "warm"}}))
    second = await trainer(
        "alpha", {"name": "Main", "min_documents": 1, "max_documents": 30, "document_ids": []}
    )
    assert second["artifact_path"] != first_artifact
    assert json.loads(Path(first_artifact).read_text(encoding="utf-8"))["tone"]["primary"] == "direct"
    assert json.loads(Path(second["artifact_path"]).read_text(encoding="utf-8"))["tone"]["primary"] == "warm"


@pytest.mark.asyncio
async def test_explicit_profile_documents_must_be_approved_and_in_project(tmp_path):
    db_path = tmp_path / "trainer.db"
    init_db(db_path)

    class Documents:
        def list(self, project_id=None, cluster=None):
            return [{"document_id": "approved", "project_id": "alpha", "cluster": "brand_voice", "approval_status": "approved", "human_rating": 5}]

    trainer = ProjectProfileTrainer(SimpleNamespace(), Documents(), BrandVoiceProfileRepository(db_path))
    with pytest.raises(ValueError, match="eligible approved brand voice documents"):
        await trainer("alpha", {"document_ids": ["foreign"], "min_documents": 1})


@pytest.mark.asyncio
async def test_failed_generation_marks_run_retryable(tmp_path):
    db_path = tmp_path / "retry.db"
    init_db(db_path)
    profiles = BrandVoiceProfileRepository(db_path)
    profile = profiles.create("alpha", "Main", {"tone": "direct"}, ["doc"])
    runs = GenerationRunRepository(db_path)
    run = runs.create("alpha", {"topic": "Topic", "keywords": ["topic"]}, "An", profile["profile_id"], 1)
    runs.set_plan(run["run_id"], "Title", "Title", ["## Intro"])

    class FailingContentService:
        async def generate_content(self, **kwargs):
            raise RuntimeError("model unavailable")

    handlers = WorkflowJobHandlers(FailingContentService(), runs, profiles)
    jobs = JobRepository(db_path)
    job = jobs.enqueue("alpha", "generate", {"run_id": run["run_id"]}, "An")
    worker = JobWorker(jobs, handlers.handle)
    await worker.run_once()

    assert jobs.get(job["job_id"])["status"] == "failed"
    assert runs.get(run["run_id"])["status"] == "failed"
    jobs.retry(job["job_id"])
    assert jobs.get(job["job_id"])["status"] == "queued"


def test_worker_recovers_jobs_left_running_by_previous_process(tmp_path):
    db_path = tmp_path / "recovery.db"
    init_db(db_path)
    jobs = JobRepository(db_path)
    job = jobs.enqueue("alpha", "plan", {"run_id": "run-1"}, "An")
    jobs.claim_next()

    assert jobs.recover_running() == 1
    assert jobs.get(job["job_id"])["status"] == "queued"


def test_worker_recovery_resets_interrupted_generation_run(tmp_path):
    db_path = tmp_path / "generation-recovery.db"
    init_db(db_path)
    runs = GenerationRunRepository(db_path)
    run = runs.create("alpha", {"topic": "Topic", "keywords": ["topic"]}, "An")
    runs.set_plan(run["run_id"], "Title", "Title", ["## Intro"])
    runs.begin_generation(run["run_id"])
    jobs = JobRepository(db_path)
    job = jobs.enqueue("alpha", "generate", {"run_id": run["run_id"]}, "An")
    jobs.claim_next()

    assert recover_interrupted_jobs(jobs, runs) == 1
    assert runs.get(run["run_id"])["status"] == "failed"
    assert jobs.get(job["job_id"])["status"] == "queued"
