from app.db.database import init_db
from app.repositories.generation_repository import GenerationRunRepository
from app.repositories.job_repository import JobRepository
from app.services.quality_gate import GenerationQualityLoop, QualityGate


def test_job_is_persisted_idempotent_and_retryable(tmp_path):
    db_path = tmp_path / "jobs.db"
    init_db(db_path)
    repository = JobRepository(db_path)

    first = repository.enqueue(
        "alpha", "generate", {"run_id": "run-1"}, "An", idempotency_key="generate:run-1"
    )
    duplicate = repository.enqueue(
        "alpha", "generate", {"run_id": "run-1"}, "An", idempotency_key="generate:run-1"
    )
    claimed = repository.claim_next()

    assert duplicate["job_id"] == first["job_id"]
    assert claimed["status"] == "running"
    assert claimed["attempts"] == 1
    assert JobRepository(db_path).get(first["job_id"])["status"] == "running"

    repository.fail(first["job_id"], {"message": "model unavailable"})
    repository.retry(first["job_id"])
    assert repository.claim_next()["attempts"] == 2
    repository.complete(first["job_id"], {"run_id": "run-1"})
    assert repository.get(first["job_id"])["result"] == {"run_id": "run-1"}


def test_generation_run_requires_review_before_publish(tmp_path):
    db_path = tmp_path / "runs.db"
    init_db(db_path)
    repository = GenerationRunRepository(db_path)
    run = repository.create(
        project_id="alpha",
        brief={"topic": "Breath support", "keywords": ["support"]},
        created_by="An",
        profile_id="profile-1",
        profile_version=2,
    )

    repository.set_outline(run["run_id"], ["## Intro", "## Practice"])
    repository.begin_generation(run["run_id"])
    repository.record_attempt(
        run["run_id"], "# Draft\n\nBody", {"passed": True, "violations": []}, "qwen3.5-2b"
    )
    repository.finalize(run["run_id"], "# Draft\n\nBody", {"passed": True}, rewrite_count=0)

    assert repository.get(run["run_id"])["status"] == "needs_review"
    try:
        repository.publish(run["run_id"])
        assert False, "publish should require approval"
    except ValueError as exc:
        assert "approved" in str(exc)

    repository.review(run["run_id"], reviewer="Binh", approved=True)
    published = repository.publish(run["run_id"])
    assert published["status"] == "published"
    assert published["reviewed_by"] == "Binh"


def test_quality_gate_reports_hard_and_dimension_failures():
    report = QualityGate().evaluate(
        "# Title\n\n# Duplicate\n\nFooter Demo - Example",
        dimension_scores={"brand": 85, "style": 79, "fingerprint": 55},
        forbidden_terms=["footer demo"],
        grounding_coverage=0.7,
        project_leakage=False,
    )

    assert report["passed"] is False
    assert {item["code"] for item in report["violations"]} >= {
        "invalid_h1_count",
        "forbidden_term",
        "style_below_threshold",
        "fingerprint_below_threshold",
        "grounding_below_threshold",
    }


def test_quality_loop_rewrites_at_most_twice_with_targeted_feedback():
    evaluations = iter(
        [
            {"passed": False, "violations": [{"code": "style_below_threshold"}]},
            {"passed": False, "violations": [{"code": "fingerprint_below_threshold"}]},
            {"passed": True, "violations": []},
        ]
    )
    feedback: list[list[str]] = []

    def generate():
        return "draft-0"

    def evaluate(_content):
        return next(evaluations)

    def rewrite(content, violation_codes):
        feedback.append(violation_codes)
        return f"{content}-rewritten"

    result = GenerationQualityLoop(evaluate=evaluate, rewrite=rewrite, max_rewrites=2).run(generate)

    assert result["rewrite_count"] == 2
    assert result["quality_report"]["passed"] is True
    assert len(result["attempts"]) == 3
    assert feedback == [["style_below_threshold"], ["fingerprint_below_threshold"]]
