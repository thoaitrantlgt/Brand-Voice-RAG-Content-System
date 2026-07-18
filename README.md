<h1 align="center">AI Content OS</h1>

<p align="center"><strong>Project-scoped, review-gated AI writing for internal content teams.</strong></p>

AI Content OS is an internal, local-first writing workflow for teams that need factual grounding, approved brand voice, repeatable review, and project isolation. It combines a FastAPI API, a separate background worker, SQLite metadata, Chroma vectors, and a Next.js operations UI.

The supported product path is asynchronous and project-scoped. It creates persisted jobs and generation runs, keeps the selected brand profile immutable for each run, records citations and quality results, and requires human approval before publishing.

> **Release status:** the fixed 25-topic release benchmark has not passed. The product is suitable for an internal pilot, not an unqualified public quality release.

## Product Model

Each project is a data and authorization boundary. Users with a scoped token can only access their assigned projects; an administrator can manage projects, profiles, and approval workflows.

The system deliberately separates two retrieval clusters:

| Cluster | Holds | Used for | Must not be used as |
| --- | --- | --- | --- |
| `knowledge` | Factual references, product material, and source documents | Grounding factual claims and collecting citations | A source of writing style |
| `brand_voice` | Explicitly approved, high-rated writing samples | Training and selecting a versioned Brand Voice Profile | A source of factual claims |

An optional `evaluation` cluster is reserved for evaluation data and is excluded from generation retrieval. The separation prevents style samples from being treated as evidence and prevents factual sources from silently defining a brand voice.

Only approved high-rated samples belong in `brand_voice`. A profile is versioned per project, and a generation run retains the exact `profile_id` and profile version used to make it reproducible.

## Asynchronous Workflow

```mermaid
flowchart LR
    A[Create project] --> B[Upload project documents]
    B --> C{Cluster}
    C -->|knowledge| D[Factual grounding]
    C -->|brand_voice, approved| E[Async profile-training job]
    E --> F[Activate immutable profile]
    F --> G[Create async generation run]
    D --> G
    G --> H[Planner job]
    H --> I[Edit outline]
    I --> J[Writer and Editor job]
    J --> K[Quality gate, citations, up to 2 rewrites]
    K --> L[Human reviewer approval]
    L --> M[Publish]
```

The API returns `202 Accepted` for queued planning, generation, and profile-training work. Start both the API process and `backend/worker.py`; the worker claims persisted jobs and advances run state.

## Features And Routes

### Product Capabilities

| Capability | What it provides |
| --- | --- |
| Project isolation | Project IDs, scoped bearer tokens, and project-filtered repositories and vectors |
| Source handling | PDF, TXT, MD, and DOCX upload, indexing, listing, search, and deletion |
| Brand voice governance | Approved sample selection, versioned profiles, explicit activation, and reviewer controls |
| Async generation | Persisted plan and generation jobs with polling, retry, restart recovery, and idempotency |
| Quality loop | Deterministic checks, grounding advisory, citations, and at most two targeted rewrites |
| Publication control | Reviewer approval is required before a generation run can publish |
| Operations | Liveness and readiness endpoints, structured logs, startup scripts, and runtime backup/restore |

### Primary API Surface

All application routes are under `/api/v1` and require a bearer token when authentication is enabled.

| Method | Route | Role | Purpose |
| --- | --- | --- | --- |
| `GET` | `/projects` | writer | List accessible projects |
| `POST` | `/projects` | admin | Create a project |
| `POST` | `/documents/upload` | writer | Upload and index a project document |
| `GET` | `/documents?project_id={id}` | writer | List project documents |
| `POST` | `/documents/search` | writer | Search a project and cluster |
| `POST` | `/projects/{project_id}/documents/{document_id}/approval` | reviewer | Approve or rate a brand sample |
| `GET` | `/projects/{project_id}/profiles` | writer | List project profile versions |
| `POST` | `/projects/{project_id}/profiles/train` | admin | Queue profile training |
| `POST` | `/projects/{project_id}/profiles/{profile_id}/activate` | admin | Activate a profile version |
| `POST` | `/projects/{project_id}/generation-runs` | writer | Create a run and queue planning |
| `GET` | `/generation-runs/{run_id}` | writer | Read a run and its quality state |
| `PATCH` | `/generation-runs/{run_id}/outline` | writer | Update a ready outline |
| `POST` | `/generation-runs/{run_id}/generate` | writer | Queue writing and editing |
| `POST` | `/generation-runs/{run_id}/review` | reviewer | Record approval, score, notes, and edits |
| `POST` | `/generation-runs/{run_id}/publish` | reviewer | Publish an approved run |
| `GET` | `/jobs/{job_id}` | writer | Poll queued, running, failed, or completed work |
| `POST` | `/jobs/{job_id}/retry` | writer | Retry an eligible failed job |

### Legacy APIs

The synchronous content endpoints, `/api/v1/content/titles`, `/api/v1/content/generate`, and `/api/v1/content/rewrite`, are legacy compatibility routes. They are disabled by default through `ENABLE_LEGACY_SYNC_API=false`; disabled requests return `404`.

The synchronous brand-profile endpoints under `/api/v1/documents/brand-voice/*` are retired. They return `410 Gone` with direction to use the project-scoped asynchronous profile workflow.

Do not build new integrations against either legacy surface. Use the project, profile, generation-run, and job routes above.

## Quick Start

### Prerequisites

- Windows PowerShell 5.1+ or PowerShell 7+
- Python 3.12-compatible environment
- Node.js compatible with Next.js 16
- LM Studio running an OpenAI-compatible local server
- A loaded model named `qwen3.5-2b`

Run repository commands from the specified directory. There is no root package manifest or root task runner.

### 1. Prepare The Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Settings load from `backend/.env`, so backend commands must run from `backend/`.

Configure LM Studio to serve `http://127.0.0.1:1234/v1`, then set the model and secure access values in `backend/.env`:

```env
RUN_MODE=cloud
AI_PROVIDER=openai
OPENAI_API_KEY=lm-studio
OPENAI_API_BASE=http://127.0.0.1:1234/v1
PLANNER_MODEL=qwen3.5-2b
WRITER_MODEL=qwen3.5-2b
EDITOR_MODEL=qwen3.5-2b
AUTH_ENABLED=true
INTERNAL_ACCESS_TOKENS={"replace-admin-token":{"username":"Admin","role":"admin","projects":["acme"]},"replace-writer-token":{"username":"Writer","role":"writer","projects":["acme"]},"replace-review-token":{"username":"Reviewer","role":"reviewer","projects":["acme"]}}
ENABLE_LEGACY_SYNC_API=false
```

`RUN_MODE=cloud` is intentional: LM Studio is accessed through an OpenAI-compatible HTTP API. `OPENAI_API_KEY` must be non-empty for the client, but LM Studio does not require a real cloud key.

### 2. Build The Frontend

```powershell
cd ..\frontend
npm install
npm.cmd run build
```

The internal startup script requires the production standalone build. It starts the API, worker, and frontend together.

### 3. Start Securely

From the repository root, use secure startup once `AUTH_ENABLED=true` and `INTERNAL_ACCESS_TOKENS` contains at least one token:

```powershell
cd ..
.\scripts\start_internal.ps1
```

Open the frontend at `http://127.0.0.1:3000`, API documentation at `http://127.0.0.1:8000/docs`, and readiness at `http://127.0.0.1:8000/ready`.

### 4. Start Insecurely For Local Development Only

An insecure session must be explicitly enabled in `backend/.env`:

```env
AUTH_ENABLED=false
ALLOW_INSECURE_AUTH=true
```

Then start only on a trusted local machine:

```powershell
.\scripts\start_internal.ps1 -AllowInsecureLocal
```

Do not use this mode on shared networks or for internal production traffic.

### 5. Stop The Stack

```powershell
.\scripts\stop_internal.ps1
```

The script stops the recorded frontend, worker, and API process IDs and removes the runtime process record.

## Configuration

`backend/.env.example` is the authoritative template. In secure deployments, set `AUTH_ENABLED=true`, supply a non-placeholder `INTERNAL_ACCESS_TOKENS` JSON registry, leave `ALLOW_INSECURE_AUTH=false` and `ENABLE_LEGACY_SYNC_API=false`, and point `PLANNER_MODEL`, `WRITER_MODEL`, and `EDITOR_MODEL` to `qwen3.5-2b`. `OPENAI_API_BASE`, `CHROMA_PERSIST_DIR`, and `UPLOAD_DIR` default to the LM Studio endpoint and local runtime locations shown above.

The application starts only when authentication has a valid token registry or insecure authentication was explicitly allowed. `start_internal.ps1` applies the same secure-start check.

## Architecture

```mermaid
flowchart TB
    UI[Next.js internal UI] --> API[FastAPI /api/v1]
    API --> Auth[Bearer token and project authorization]
    API --> SQLite[(SQLite metadata and job state)]
    API --> Chroma[(Chroma project-scoped vectors)]
    Worker[Python background worker] --> SQLite
    Worker --> LLM[LM Studio: qwen3.5-2b]
    Worker --> Chroma
    Worker --> SQLite
    API --> Ready[/ready checks/]
    Ready --> SQLite
    Ready --> Chroma
    Ready --> LLM
```

`frontend/` provides the operations UI; `backend/app/api/v1/` exposes routers; `backend/worker.py` consumes jobs; `backend/app/workers/` executes planning, generation, and training; and `backend/app/rag/` handles documents, embeddings, and filtered retrieval. SQLite owns transactional metadata and state transitions, while Chroma stores vectors with project, cluster, document, and profile metadata.

## API Workflow

This example uses PowerShell and a secure token. Replace placeholders before running it.

```powershell
$api = 'http://127.0.0.1:8000/api/v1'
$adminHeaders = @{ Authorization = 'Bearer replace-admin-token'; 'Content-Type' = 'application/json' }
$writerHeaders = @{ Authorization = 'Bearer replace-writer-token'; 'Content-Type' = 'application/json' }
$reviewerHeaders = @{ Authorization = 'Bearer replace-review-token'; 'Content-Type' = 'application/json' }
```

Create the `acme` project before using the project-scoped routes:

```powershell
Invoke-RestMethod -Method Post -Uri "$api/projects" -Headers $adminHeaders -Body (@{
  project_id = 'acme'
  name = 'Acme Content'
  description = 'Internal content operations'
} | ConvertTo-Json)
```

### Upload Sources Into The Right Cluster

```powershell
Invoke-RestMethod -Method Post -Uri "$api/documents/upload" `
  -Headers $writerHeaders `
  -Form @{ file = Get-Item 'C:\sources\product-facts.pdf'; project_id = 'acme'; cluster = 'knowledge' }
```

Use the same endpoint with `cluster = 'brand_voice'` only for approved, high-rated writing samples. Record sample approval and a human rating through `/projects/{project_id}/documents/{document_id}/approval` before training.

### Queue And Activate A Profile

```powershell
Invoke-RestMethod -Method Post -Uri "$api/projects/acme/profiles/train" `
  -Headers $adminHeaders `
  -Body (@{ name = 'Acme editorial voice' } | ConvertTo-Json)
```

Poll the returned `job.job_id`, then list profiles before selecting one to activate:

```powershell
$profiles = Invoke-RestMethod -Uri "$api/projects/acme/profiles" -Headers $writerHeaders
$profileId = $profiles[0].profile_id
Invoke-RestMethod -Method Post -Uri "$api/projects/acme/profiles/$profileId/activate" -Headers $adminHeaders
```

### Create, Plan, And Generate A Run

```powershell
$run = Invoke-RestMethod -Method Post -Uri "$api/projects/acme/generation-runs" `
  -Headers $writerHeaders `
  -Body (@{
    topic = 'How to evaluate product documentation'
    keywords = @('documentation', 'evaluation')
    audience = 'Product leaders'
    objective = 'Provide a practical internal evaluation checklist.'
    channel = 'blog'
  } | ConvertTo-Json)

Invoke-RestMethod -Uri "$api/jobs/$($run.job.job_id)" -Headers $writerHeaders
```

After planning reaches `outline_ready`, edit the outline if needed and queue generation:

```powershell
Invoke-RestMethod -Method Patch -Uri "$api/generation-runs/$($run.run_id)/outline" `
  -Headers $writerHeaders `
  -Body (@{ outline = @('# Working outline', '## Section one') } | ConvertTo-Json)

Invoke-RestMethod -Method Post -Uri "$api/generation-runs/$($run.run_id)/generate" `
  -Headers $writerHeaders
```

Read the run and its job until generation completes; it exposes content, citations, quality information, profile identity, rewrite count, and state.

### Review And Publish

```powershell
Invoke-RestMethod -Method Post -Uri "$api/generation-runs/$($run.run_id)/review" `
  -Headers $reviewerHeaders `
  -Body (@{ approved = $true; human_score = 4; notes = 'Approved for internal publication.' } | ConvertTo-Json)

Invoke-RestMethod -Method Post -Uri "$api/generation-runs/$($run.run_id)/publish" `
  -Headers $reviewerHeaders
```

Publication is guarded: a run without reviewer approval receives a conflict response instead of publishing.

## Evaluation Evidence

The following evidence demonstrates a working smoke path. It is not a claim that the release gate has been met.

| Verified item | Result |
| --- | --- |
| Backend suite | 50 tests verified |
| Readiness model | `qwen3.5-2b` available through LM Studio readiness checks |
| TSS smoke brand score | 87 |
| TSS smoke style score | 92 |
| TSS smoke writing fingerprint score | 45 |
| TSS smoke persona score | 55 |
| TSS smoke grounding coverage | 1.0 |
| TSS smoke citations | 2 |
| Targeted rewrites | 2 maximum attempts |
| Publication control | Human approval required |

The TSS smoke result confirms that the end-to-end flow can obtain citations, complete quality processing, and preserve review controls. It does not demonstrate broad quality, reliable fingerprint matching, or a passed release benchmark.

The fixed 25-topic release benchmark remains outstanding. Until it passes, use this product as an internal pilot with reviewer oversight rather than as an unqualified public quality release.

For evaluation methodology, quality thresholds, data splits, and known limits, read [PIPELINE_EVALUATION_PLAN.md](PIPELINE_EVALUATION_PLAN.md).

## Operations

### Health And Readiness

| Endpoint | Meaning |
| --- | --- |
| `GET /health` | Process liveness and configured provider information |
| `GET /ready` | SQLite, vector storage, and expected LM Studio model readiness |

Use `/ready` for operational readiness. A live API can still be unready if its database, vector store, or expected `qwen3.5-2b` model is unavailable.

### Logs And Process Management

`scripts/start_internal.ps1` writes process IDs to `.runtime/processes.json` and redirects output to `.runtime/logs/`. It starts the API from `backend/run.py`, the worker from `backend/worker.py`, and the standalone Next.js server.

The frontend production build must exist before startup. The script copies static build assets into the standalone output and rejects an unsafe auth configuration unless `-AllowInsecureLocal` is specified.

### Backup

From the repository root, create a runtime backup after stopping write-heavy activity. Pass backend data and configuration paths explicitly because the script resolves its defaults from its working directory:

```powershell
.\backend\.venv\Scripts\python.exe .\backend\scripts\backup_runtime.py backup `
  --data-dir .\backend\data `
  --config-dir .\backend\config `
  --backup-dir .\backups\contentos-YYYYMMDD
```

The backup includes the SQLite database, Chroma data, uploads, generated brand artifacts, configuration, and a manifest. Use a new empty target directory for each backup.

Restore only into a planned maintenance window:

```powershell
.\backend\.venv\Scripts\python.exe .\backend\scripts\backup_runtime.py restore `
  --data-dir .\backend\data `
  --config-dir .\backend\config `
  --backup-dir .\backups\contentos-YYYYMMDD `
  --force
```

`--force` replaces existing runtime destinations. Verify the chosen backup and target before using it.

### Containers

The repository includes `backend/Dockerfile` and `frontend/Dockerfile` for container builds. Persistent SQLite, Chroma, upload, and configuration directories remain required for operational continuity; containerization does not remove the need for backups or readiness checks.

## Security

- Keep `AUTH_ENABLED=true` outside isolated local development.
- Store non-placeholder `INTERNAL_ACCESS_TOKENS` outside source control and rotate them through the team secret process.
- Assign the least privileged role: writer, reviewer, or admin.
- Limit each token to the projects it needs; `*` grants access to all projects.
- Treat `project_id` as a hard data boundary for documents, vectors, profiles, jobs, runs, and blogs.
- Keep factual material in `knowledge` and approved samples in `brand_voice`; never use either cluster as a substitute for the other.
- Require reviewer approval before publishing, even after automated checks pass.
- Use `ALLOW_INSECURE_AUTH=true` and `-AllowInsecureLocal` only together, only on a trusted local machine.
- Do not expose LM Studio, SQLite files, Chroma persistence, or uploads directly to untrusted networks.

## Testing

Run backend tests from `backend/`. The suite mocks RAG and vector dependencies and does not require API keys or a live Chroma service.

```powershell
cd backend
$env:DEBUG = 'false'
.\.venv\Scripts\python.exe -m pytest tests\test_health.py -v
.\.venv\Scripts\python.exe -m pytest
```

The verified baseline is 50 backend tests. Run the focused test first when working on a related backend area, then run the full suite when practical.

Run frontend checks from `frontend/`:

```powershell
cd frontend
npm.cmd run lint
npm.cmd run build
```

Use `npm.cmd` on Windows if PowerShell execution policy blocks `npm.ps1`.

## Release Checklist

- [ ] Use a secure `.env`: authentication enabled, valid scoped tokens, and legacy sync APIs disabled.
- [ ] Build the frontend production output with `npm.cmd run build`.
- [ ] Start the API, worker, and frontend with `scripts/start_internal.ps1`.
- [ ] Confirm `/health` is live and `/ready` verifies SQLite, Chroma, and `qwen3.5-2b`.
- [ ] Verify `knowledge` sources are factual and `brand_voice` samples are explicitly approved and high-rated.
- [ ] Train and activate the intended immutable profile version for each project.
- [ ] Verify planning, generation, citation capture, bounded rewrites, human review, and guarded publishing.
- [ ] Run focused and full backend tests, then frontend lint and build checks.
- [ ] Create and validate a runtime backup.
- [ ] Run the fixed 25-topic release benchmark and record results.
- [ ] Do not claim a public quality release until that benchmark passes and reviewer evidence supports it.

## Further Reading

- [Pipeline evaluation plan](PIPELINE_EVALUATION_PLAN.md): project data model, cluster separation, evaluation criteria, and benchmark context.
- [Internal ship-ready plan](docs/superpowers/plans/2026-07-17-internal-ship-ready.md): architecture, operational constraints, and implementation milestones.
- [README redesign specification](docs/superpowers/specs/2026-07-18-readme-redesign-design.md): scope and editorial requirements for this guide.
