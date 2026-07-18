from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import Principal
from app.core.dependencies import authorize, authorize_project, get_current_principal
from app.repositories.brand_voice_profile_repository import BrandVoiceProfileRepository
from app.repositories.generation_repository import GenerationRunRepository
from app.repositories.job_repository import JobRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.document_repository import DocumentRepository
from app.schemas.workflow import (
    ContentBrief,
    JobEnvelope,
    OutlineUpdate,
    ProfileTrainRequest,
    ProjectCreate,
    ReviewRequest,
    DocumentApprovalRequest,
)


router = APIRouter(tags=["Internal Workflow"])


def get_project_repo() -> ProjectRepository:
    return ProjectRepository()


def get_profile_repo() -> BrandVoiceProfileRepository:
    return BrandVoiceProfileRepository()


def get_generation_repo() -> GenerationRunRepository:
    return GenerationRunRepository()


def get_job_repo() -> JobRepository:
    return JobRepository()


def get_document_repo() -> DocumentRepository:
    return DocumentRepository()


def _run_or_404(repository: GenerationRunRepository, run_id: str, principal: Principal):
    run = repository.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Generation run not found")
    authorize_project(principal, run["project_id"])
    return run


@router.get("/projects")
def list_projects(
    principal: Principal = Depends(get_current_principal),
    repository: ProjectRepository = Depends(get_project_repo),
):
    authorize(principal, "writer")
    projects = repository.list()
    if "*" in principal.projects:
        return projects
    return [item for item in projects if item["project_id"] in principal.projects]


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(
    request: ProjectCreate,
    principal: Principal = Depends(get_current_principal),
    repository: ProjectRepository = Depends(get_project_repo),
):
    authorize(principal, "admin")
    try:
        return repository.create(request.project_id, request.name, request.description)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/projects/{project_id}/profiles")
def list_profiles(
    project_id: str,
    principal: Principal = Depends(get_current_principal),
    repository: BrandVoiceProfileRepository = Depends(get_profile_repo),
):
    authorize(principal, "writer")
    authorize_project(principal, project_id)
    return repository.list(project_id)


@router.post("/projects/{project_id}/profiles/train", response_model=JobEnvelope, status_code=202)
def train_profile(
    project_id: str,
    request: ProfileTrainRequest,
    principal: Principal = Depends(get_current_principal),
    projects: ProjectRepository = Depends(get_project_repo),
    jobs: JobRepository = Depends(get_job_repo),
):
    authorize(principal, "admin")
    authorize_project(principal, project_id)
    if projects.get(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    job = jobs.enqueue(
        project_id,
        "train_profile",
        request.model_dump(),
        principal.username,
        idempotency_key=None,
    )
    return JobEnvelope(job=job)


@router.post("/projects/{project_id}/profiles/{profile_id}/activate")
def activate_profile(
    project_id: str,
    profile_id: str,
    principal: Principal = Depends(get_current_principal),
    repository: BrandVoiceProfileRepository = Depends(get_profile_repo),
):
    authorize(principal, "admin")
    authorize_project(principal, project_id)
    try:
        return repository.activate(project_id, profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/projects/{project_id}/documents/{document_id}/approval")
def approve_document(
    project_id: str,
    document_id: str,
    request: DocumentApprovalRequest,
    principal: Principal = Depends(get_current_principal),
    repository: DocumentRepository = Depends(get_document_repo),
):
    authorize(principal, "reviewer")
    authorize_project(principal, project_id)
    try:
        updated = repository.set_approval(
            project_id, document_id, request.status, request.human_rating
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Brand voice document not found")
    return repository.get(document_id)


@router.post(
    "/projects/{project_id}/generation-runs",
    response_model=JobEnvelope,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_generation_run(
    project_id: str,
    brief: ContentBrief,
    principal: Principal = Depends(get_current_principal),
    projects: ProjectRepository = Depends(get_project_repo),
    profiles: BrandVoiceProfileRepository = Depends(get_profile_repo),
    runs: GenerationRunRepository = Depends(get_generation_repo),
    jobs: JobRepository = Depends(get_job_repo),
):
    authorize(principal, "writer")
    authorize_project(principal, project_id)
    if projects.get(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    profile = profiles.get(project_id, brief.profile_id) if brief.profile_id else profiles.get_active(project_id)
    if profile is None:
        raise HTTPException(status_code=422, detail="Project requires an active brand voice profile")
    run = runs.create(
        project_id,
        brief.model_dump(exclude={"profile_id"}),
        principal.username,
        profile["profile_id"],
        profile["version"],
    )
    job = jobs.enqueue(
        project_id,
        "plan",
        {"run_id": run["run_id"]},
        principal.username,
        idempotency_key=f"plan:{run['run_id']}",
    )
    return JobEnvelope(run_id=run["run_id"], job=job)


@router.get("/generation-runs/{run_id}")
def get_generation_run(
    run_id: str,
    principal: Principal = Depends(get_current_principal),
    repository: GenerationRunRepository = Depends(get_generation_repo),
):
    authorize(principal, "writer")
    return _run_or_404(repository, run_id, principal)


@router.get("/projects/{project_id}/generation-runs")
def list_generation_runs(
    project_id: str,
    limit: int = 50,
    principal: Principal = Depends(get_current_principal),
    repository: GenerationRunRepository = Depends(get_generation_repo),
):
    authorize(principal, "writer")
    authorize_project(principal, project_id)
    return repository.list(project_id, max(1, min(limit, 100)))


@router.patch("/generation-runs/{run_id}/outline")
def update_outline(
    run_id: str,
    request: OutlineUpdate,
    principal: Principal = Depends(get_current_principal),
    repository: GenerationRunRepository = Depends(get_generation_repo),
):
    authorize(principal, "writer")
    _run_or_404(repository, run_id, principal)
    try:
        return repository.set_outline(run_id, request.outline)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/generation-runs/{run_id}/generate", response_model=JobEnvelope, status_code=202)
def enqueue_generation(
    run_id: str,
    principal: Principal = Depends(get_current_principal),
    runs: GenerationRunRepository = Depends(get_generation_repo),
    jobs: JobRepository = Depends(get_job_repo),
):
    authorize(principal, "writer")
    run = _run_or_404(runs, run_id, principal)
    if run["status"] != "outline_ready":
        raise HTTPException(status_code=409, detail="Outline must be ready before generation")
    job = jobs.enqueue(
        run["project_id"],
        "generate",
        {"run_id": run_id},
        principal.username,
        idempotency_key=f"generate:{run_id}",
    )
    return JobEnvelope(run_id=run_id, job=job)


@router.post("/generation-runs/{run_id}/review")
def review_generation(
    run_id: str,
    request: ReviewRequest,
    principal: Principal = Depends(get_current_principal),
    repository: GenerationRunRepository = Depends(get_generation_repo),
):
    authorize(principal, "reviewer")
    _run_or_404(repository, run_id, principal)
    try:
        return repository.review(
            run_id,
            principal.username,
            request.approved,
            request.human_score,
            request.notes,
            request.edited_content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/generation-runs/{run_id}/publish")
def publish_generation(
    run_id: str,
    principal: Principal = Depends(get_current_principal),
    repository: GenerationRunRepository = Depends(get_generation_repo),
):
    authorize(principal, "reviewer")
    _run_or_404(repository, run_id, principal)
    try:
        return repository.publish(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/jobs/{job_id}")
def get_job(
    job_id: str,
    principal: Principal = Depends(get_current_principal),
    repository: JobRepository = Depends(get_job_repo),
):
    authorize(principal, "writer")
    job = repository.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    authorize_project(principal, job["project_id"])
    return job


@router.post("/jobs/{job_id}/retry")
def retry_job(
    job_id: str,
    principal: Principal = Depends(get_current_principal),
    repository: JobRepository = Depends(get_job_repo),
):
    authorize(principal, "writer")
    job = repository.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    authorize_project(principal, job["project_id"])
    try:
        repository.retry(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return repository.get(job_id)
