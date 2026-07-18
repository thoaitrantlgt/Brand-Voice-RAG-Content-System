# Internal Ship-Ready Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a single-machine internal AI Content OS with project-isolated data, versioned brand profiles, asynchronous generation, quality rewrites, and mandatory human approval.

**Architecture:** FastAPI remains the API boundary, SQLite owns transactional metadata and persisted jobs, Chroma stores project-scoped vectors, and a separate worker runs LM Studio jobs. Next.js consumes the asynchronous APIs and exposes source, profile, generation, and review workflows.

**Tech Stack:** Python 3.12, FastAPI, SQLite, ChromaDB, CrewAI, LM Studio/OpenAI-compatible API, Next.js 16, React 19, TypeScript.

## Global Constraints

- Runtime model is `qwen3.5-2b` through LM Studio on the same internal machine.
- Knowledge, brand voice, and evaluation clusters must never be mixed during generation.
- Automated evaluation is advisory; a reviewer or admin must approve before publishing.
- Targeted rewrite is limited to two attempts.
- Production APIs require bearer-token roles: writer, reviewer, or admin.
- Preserve existing synchronous APIs for development compatibility, but the production UI uses persisted jobs.

---

### Task 1: Persistence, profile versioning, and authentication

- [ ] Add failing migration, profile isolation, and token-role tests.
- [ ] Add versioned SQLite migrations and repositories.
- [ ] Add bearer-token principal resolution and role dependencies.
- [ ] Run focused and full backend tests.

### Task 2: Persisted generation jobs and quality loop

- [ ] Add failing job lifecycle and generation state-machine tests.
- [ ] Add job/generation repositories and worker entrypoint.
- [ ] Add deterministic quality gate, grounding advisory, and two targeted rewrites.
- [ ] Verify restart, retry, and idempotency behavior.

### Task 3: Project, profile, generation, review, and publish APIs

- [ ] Add failing API authorization and workflow tests.
- [ ] Add project-scoped routers and schemas.
- [ ] Enforce reviewer approval before publish.
- [ ] Keep legacy synchronous endpoints behind configuration.

### Task 4: Internal product frontend

- [ ] Add a shared environment-driven API client and project context.
- [ ] Build Sources and Profile workflows.
- [ ] Convert Create to plan/generate job polling.
- [ ] Build Review and guarded publishing workflows.
- [ ] Run lint, production build, and Playwright smoke checks.

### Task 5: Operations and release verification

- [ ] Add API, worker, and frontend containers with persistent volumes.
- [ ] Add model/database/vector readiness and structured job logging.
- [ ] Add backup and restore scripts.
- [ ] Run all tests and the 25-topic release benchmark.
- [ ] Record release-gate metrics and unresolved risks.
