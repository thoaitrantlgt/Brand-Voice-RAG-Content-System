# README Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the repository README with a polished English product-and-developer guide that accurately documents the shipped asynchronous workflow.

**Architecture:** Keep `README.md` as the concise entry point and link to existing pipeline/specification documents for deep evaluation details. Validate every documented command, route, model name, file path, and quality claim against the current repository.

**Tech Stack:** GitHub Flavored Markdown, Mermaid, shields.io badges, PowerShell verification commands.

## Global Constraints

- Write entirely in English and target approximately 300 to 400 lines.
- Describe only behavior present in the current repository.
- Present project-scoped asynchronous APIs as the supported workflow.
- Do not claim that the 25-topic quality release gate has passed.
- Preserve the verified 50-test result, Qwen3.5-2B readiness, and TSS smoke scores.
- Do not add application dependencies, stock images, or decorative assets.

---

### Task 1: Rewrite the Product and Developer Guide

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: Current routes, scripts, settings, and verification evidence in the repository.
- Produces: A single English onboarding document linking to deeper plans and evaluation material.

- [ ] **Step 1: Replace the legacy README structure**

Write these sections in order: product header, product model, workflow diagram, features and routes, quick start, configuration, architecture, API workflow, evaluation evidence, operations, security, testing, release checklist, and further reading.

- [ ] **Step 2: Keep all claims evidence-based**

Document the smoke scores as `brand 87`, `style 92`, `fingerprint 45`, `persona 55`, and `grounding 1.0`. State that the smoke run required human approval and that the fixed 25-topic release benchmark remains outstanding.

- [ ] **Step 3: Keep setup commands executable**

Use repository-relative PowerShell commands for `backend/.venv`, `npm.cmd run build`, `scripts/start_internal.ps1`, `scripts/stop_internal.ps1`, and `backend/scripts/backup_runtime.py`.

### Task 2: Validate and Publish the Documentation

**Files:**
- Verify: `README.md`
- Verify: `backend/.env.example`
- Verify: `backend/app/api/v1/workflow_router.py`
- Verify: `scripts/start_internal.ps1`

**Interfaces:**
- Consumes: The README produced by Task 1.
- Produces: A reviewed commit merged into `main` and pushed to `origin/main`.

- [ ] **Step 1: Check document shape and stale references**

Run:

```powershell
(Get-Content README.md).Count
rg -n "^#|qwen3-1.7b|/content/titles|/documents/brand-voice/train|TBD|TODO" README.md
```

Expected: 300-400 lines, coherent headings, no stale model name, and legacy endpoints mentioned only as disabled behavior if present.

- [ ] **Step 2: Verify referenced paths**

Run:

```powershell
Test-Path backend\.env.example
Test-Path backend\worker.py
Test-Path scripts\start_internal.ps1
Test-Path backend\scripts\backup_runtime.py
Test-Path PIPELINE_EVALUATION_PLAN.md
```

Expected: every result is `True`.

- [ ] **Step 3: Inspect the final diff**

Run:

```powershell
git diff --check
git diff -- README.md
```

Expected: no whitespace errors and only the intended README rewrite plus its approved design/plan documents.

- [ ] **Step 4: Commit and integrate**

```powershell
git add README.md docs/superpowers/plans/2026-07-18-readme-redesign.md
git commit -m "docs: redesign project README"
git checkout main
git merge --ff-only feat/internal-ship-ready
git push origin main
```

Expected: `main` and `origin/main` resolve to the same final commit.
