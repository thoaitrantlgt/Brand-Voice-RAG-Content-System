from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.workflow_router import (
    get_generation_repo,
    get_job_repo,
    get_profile_repo,
    get_project_repo,
    router,
)
from app.core.auth import Principal
from app.core.dependencies import get_current_principal
from app.db.database import init_db
from app.repositories.brand_voice_profile_repository import BrandVoiceProfileRepository
from app.repositories.generation_repository import GenerationRunRepository
from app.repositories.job_repository import JobRepository
from app.repositories.project_repository import ProjectRepository


def _client(tmp_path, principal: Principal):
    db_path = tmp_path / "api.db"
    init_db(db_path)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_principal] = lambda: principal
    app.dependency_overrides[get_project_repo] = lambda: ProjectRepository(db_path)
    app.dependency_overrides[get_profile_repo] = lambda: BrandVoiceProfileRepository(db_path)
    app.dependency_overrides[get_generation_repo] = lambda: GenerationRunRepository(db_path)
    app.dependency_overrides[get_job_repo] = lambda: JobRepository(db_path)
    return TestClient(app), db_path


def test_only_admin_can_create_project(tmp_path):
    client, _ = _client(tmp_path, Principal("An", "writer"))
    response = client.post("/api/v1/projects", json={"project_id": "alpha", "name": "Alpha"})
    assert response.status_code == 403


def test_run_and_job_ids_cannot_cross_project_boundary(tmp_path):
    admin, db_path = _client(tmp_path, Principal("Admin", "admin"))
    for project_id in ("alpha", "beta"):
        admin.post("/api/v1/projects", json={"project_id": project_id, "name": project_id})
        profiles = BrandVoiceProfileRepository(db_path)
        profile = profiles.create(project_id, "Main", {"tone": "direct"}, ["doc-1"])
        profiles.activate(project_id, profile["profile_id"])
    created = admin.post(
        "/api/v1/projects/alpha/generation-runs",
        json={"topic": "Breath support", "keywords": ["breath"], "audience": "singers", "objective": "teach"},
    ).json()

    beta_client, _ = _client(tmp_path, Principal("Beta", "writer", frozenset({"beta"})))
    assert beta_client.get(f"/api/v1/generation-runs/{created['run_id']}").status_code == 403
    assert beta_client.get(f"/api/v1/jobs/{created['job']['job_id']}").status_code == 403


def test_generation_api_enqueues_jobs_and_requires_review_before_publish(tmp_path):
    client, db_path = _client(tmp_path, Principal("Admin", "admin"))
    assert client.post(
        "/api/v1/projects", json={"project_id": "alpha", "name": "Alpha"}
    ).status_code == 201
    profile_repo = BrandVoiceProfileRepository(db_path)
    profile = profile_repo.create("alpha", "Main", {"tone": "direct"}, ["doc-1"])
    profile_repo.activate("alpha", profile["profile_id"])

    created = client.post(
        "/api/v1/projects/alpha/generation-runs",
        json={
            "topic": "Breath support",
            "keywords": ["breath support"],
            "audience": "voice students",
            "objective": "teach a safe exercise",
            "category": "practice",
        },
    )
    assert created.status_code == 202
    run_id = created.json()["run_id"]
    assert created.json()["job"]["status"] == "queued"

    outline = client.patch(
        f"/api/v1/generation-runs/{run_id}/outline",
        json={"outline": ["## Why support matters", "## Practice"]},
    )
    assert outline.status_code == 200
    queued = client.post(f"/api/v1/generation-runs/{run_id}/generate")
    assert queued.status_code == 202
    assert queued.json()["job"]["job_type"] == "generate"

    runs = GenerationRunRepository(db_path)
    runs.begin_generation(run_id)
    runs.record_attempt(run_id, "# Draft\n\nBody", {"passed": True}, "qwen3.5-2b")
    runs.finalize(run_id, "# Draft\n\nBody", {"passed": True}, 0)

    assert client.post(f"/api/v1/generation-runs/{run_id}/publish").status_code == 409
    reviewed = client.post(
        f"/api/v1/generation-runs/{run_id}/review",
        json={"approved": True, "human_score": 90, "notes": "Ready"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "approved"
    published = client.post(f"/api/v1/generation-runs/{run_id}/publish")
    assert published.status_code == 200
    assert published.json()["status"] == "published"
