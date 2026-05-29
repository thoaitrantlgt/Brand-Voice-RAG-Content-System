# AI Content Blog OS

AI Content Blog OS is a full-stack application for creating and managing blog posts with a Multi-Agent AI workflow. The backend uses FastAPI for AI orchestration, RAG, and blog storage. The frontend uses Next.js for the dashboard, article creation flow, blog management, and document upload.

## Features

- Dashboard powered by real backend data: blog counts, drafts, published posts, RAG documents, indexed chunks, and system health.
- Blog creation flow: enter keywords -> AI researches web/uploaded documents -> generate a draft outline -> user feedback -> Writer + Editor agents create the final article.
- Upload PDF/TXT/MD/DOCX documents into the Knowledge Hub so AI can reference them during planning and writing.
- Train a Brand Voice Profile from existing high-quality blog documents, then use it as a hard writing constraint for future content.
- Evaluate generated drafts against the active brand voice before publishing.
- Export SFT and DPO seed datasets for later supervised fine-tuning or preference optimization.
- Blog management: view, edit, delete, save as draft, and publish.
- Inline AI rewrite: select a paragraph and ask AI to rewrite it based on feedback.

## Project Structure

```text
.
├── backend/   # FastAPI, CrewAI, RAG, SQLite blog storage
├── frontend/  # Next.js, React, Tailwind CSS
├── AGENTS.md  # Repository operating notes for coding agents
└── README.md
```

There is no root task runner. Run backend commands from `backend/` and frontend commands from `frontend/`.

## Requirements

- Python 3.12+
- Node.js + npm
- A configured LLM provider or local OpenAI-compatible server
- Optional: `SERPER_API_KEY` for Web Search

## Run The Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
.\.venv\Scripts\python.exe run.py
```

The backend runs at:

```text
http://127.0.0.1:8000
```

Main routes:

- `GET /health`
- `POST /api/v1/content/titles` - generate a draft outline from keywords
- `POST /api/v1/content/generate` - generate a complete article from an approved draft
- `POST /api/v1/content/rewrite` - rewrite selected text
- `GET/POST/PUT/DELETE /api/v1/blogs`
- `GET/POST/DELETE /api/v1/documents`
- `POST /api/v1/documents/brand-voice/train` - build a Brand Voice Profile from indexed documents
- `GET /api/v1/documents/brand-voice/profile` - fetch the active Brand Voice Profile
- `POST /api/v1/documents/brand-voice/evaluate` - score content against the active Brand Voice Profile

Important: backend settings are loaded from `.env` in the current working directory, so run backend commands from `backend/`.

## Set Up LM Studio As A Local API

This project can use LM Studio as an OpenAI-compatible API server. In this mode, keep `AI_PROVIDER=openai` and point `OPENAI_API_BASE` to LM Studio's local server.

### 1. Prepare LM Studio

1. Install LM Studio.
2. Download a chat/instruct model, for example `qwen3-1.7b` or any model your machine can run.
3. Open the Developer or Local Server tab.
4. Load the model.
5. Start the OpenAI-compatible server.
6. Keep the default port `1234`, which gives you:

```text
http://127.0.0.1:1234/v1
```

You can verify the server with:

```powershell
curl http://127.0.0.1:1234/v1/models
```

### 2. Configure `backend/.env`

Use this configuration in `backend/.env`:

```env
RUN_MODE=cloud
AI_PROVIDER=openai

OPENAI_API_KEY=dummy_key_for_local_server
OPENAI_API_BASE=http://127.0.0.1:1234/v1

PLANNER_MODEL=qwen3-1.7b
WRITER_MODEL=qwen3-1.7b
EDITOR_MODEL=qwen3-1.7b

DEBUG=false
```

Notes:

- `RUN_MODE=cloud` is correct for LM Studio in this repo because the backend calls LM Studio through an OpenAI-compatible HTTP API.
- `OPENAI_API_KEY` still needs any non-empty value because OpenAI-compatible clients usually require the field.
- `PLANNER_MODEL`, `WRITER_MODEL`, and `EDITOR_MODEL` should match the model name returned by LM Studio from `/v1/models`.
- If you change the LM Studio port, update `OPENAI_API_BASE`.
- `DEBUG` must be a valid boolean: `true` or `false`.

### 3. Run The App With LM Studio

Recommended order:

1. Open LM Studio and start the server.
2. Run the backend from `backend/`:

```powershell
.\.venv\Scripts\python.exe run.py
```

3. Run the frontend from `frontend/`:

```powershell
npm run dev
```

When you create an article at `/create`, the backend will call the model currently loaded in LM Studio to plan drafts, write content, and rewrite text.

## Run The Frontend

```powershell
cd frontend
npm install
npm run dev
```

The frontend runs at:

```text
http://127.0.0.1:3000
```

Main pages:

- `/` - Dashboard
- `/create` - Create a blog post
- `/blogs` - Manage blog posts
- `/rag` - Upload and search documents

The frontend currently calls the backend at `http://127.0.0.1:8000/api/v1`.

## Blog Creation Workflow

1. Go to `/create`.
2. Enter the main keywords. Multiple keywords can be separated with commas.
3. Enable Web Search if you want AI to use updated web information.
4. The Planner Agent searches the web or uploaded documents in the Knowledge Hub.
5. The system creates one draft with a title, SEO title, headings, and bullet points.
6. The user edits the draft/outline.
7. Writer + Editor agents generate the complete article.
8. The user can preview, edit Markdown, rewrite selected paragraphs, save as draft, or publish.

## Corporate Style Guide

The project includes an enterprise-style content guardrail system. The source of truth is:

```text
backend/config/corporate_style_guide.json
```

It defines:

- Allowed terms that the model should prefer.
- Forbidden terms and deterministic replacements.
- Style rules such as tone, expertise level, maximum sentence length, and writing principles.

Backend configuration:

```env
STYLE_GUIDE_PATH=./config/corporate_style_guide.json
```

How it is enforced:

1. Pre-generation: the Writer and Editor tasks receive the corporate style guide in their prompts.
2. Post-generation: backend code scans the final Markdown and automatically replaces forbidden terms.
3. The API returns `style_report`, including style score, replacements, remaining forbidden terms, and sentence warnings.
4. The `/create` page shows a Corporate Style panel after content generation.

This combines prompt engineering with deterministic code checks, which is safer than relying only on the LLM to remember every rule.

## Brand Voice Training

The Knowledge Hub can now train a reusable Brand Voice Profile from your previous high-quality content. This follows the workflow described in Search Engine Land's guide to training in-house LLMs on brand voice:

```text
Upload best content -> Extract brand patterns -> Build profile -> Index profile into RAG -> Generate/evaluate content
```

Recommended source data:

- Use 20-30 of your strongest blog posts or brand-approved documents.
- Prefer complete articles with intro, body sections, examples, and conclusion intact.
- Choose content that performed well or best represents the company's voice.
- Remove outdated, weak, duplicated, or off-brand examples before training.

When uploading documents, choose a document purpose:

- `knowledge`: source material for RAG while writing, such as product docs, reports, research, or customer insights.
- `brand_voice`: approved writing samples used only for Brand Voice Training.
- `both`: material that is both factually useful and a strong example of the company's voice.

Brand Voice Training only uses documents marked `brand_voice` or `both`. This keeps technical references or product PDFs from contaminating the tone profile.

### Train From The UI

1. Start the backend and frontend.
2. Go to `/rag`.
3. Upload your best blog documents into the Knowledge Hub.
4. Mark tone samples as `Brand Voice` or `Both`.
5. Click `Train Brand Voice`.
6. The profile is saved, indexed into ChromaDB, and automatically used by future Writer/Editor prompts.

### Train From The API

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/documents/brand-voice/train `
  -H "Content-Type: application/json" `
  -d '{
    "company_name": "Your Company",
    "document_ids": [],
    "min_documents": 20,
    "max_documents": 30,
    "target_audience": "Marketing managers and business leaders",
    "brand_values": ["clear", "practical", "trustworthy"],
    "channels": ["blog", "email", "social", "support", "ads"]
  }'
```

Notes:

- `document_ids: []` means "use all indexed documents marked `brand_voice` or `both`."
- If fewer than `min_documents` are available, training still runs but returns a warning.
- The LLM extraction step has a deterministic fallback, so the pipeline can still produce a starter profile if the LLM call fails.

### What The Profile Contains

The generated Brand Voice Profile includes:

- Tone profile: primary tone, secondary tone traits, and description.
- Vocabulary: repeated terms, preferred phrases, forbidden terms, and replacements.
- Syntax: sentence rhythm, average sentence length, and writing rules.
- Presentation rules: heading style, list style, chart intro style, and article flow.
- Strategic context: target audience, brand values, interaction style, and message architecture.
- Channel guidance: blog, email, social, support, and ads voice adjustments.
- Prompt templates for common content types.
- 10 calibration prompts for testing whether the system stays on-brand.
- Governance checklist and RACI-style ownership notes for human review.
- Training method recommendation: prompt engineering, RAG, PEFT, or full fine-tuning based on available data volume.

Generated files:

```text
backend/config/brand_voice_profile.json
backend/data/brand_voice/brand_voice_sft.jsonl
backend/data/brand_voice/brand_voice_dpo_seed.jsonl
```

The SFT dataset uses the approved source articles as assistant responses. The DPO file is a seed preference dataset and should be reviewed by a human before any real DPO training run.

### Evaluate Drafts Before Publishing

Use the evaluation endpoint to check whether a generated draft matches the active Brand Voice Profile:

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/documents/brand-voice/evaluate `
  -H "Content-Type: application/json" `
  -d '{
    "channel": "blog",
    "content_type": "blog_post",
    "content": "# Example Title\n\n## Section\n\nYour generated draft here..."
  }'
```

The response includes:

- `overall_score`
- `dimension_scores` for tone, vocabulary, readability, structure, and channel fit
- voice violations
- improvement recommendations
- human reviewer checklist

Use this score as a pre-publish guardrail, not as a replacement for editorial review.

## Testing

Backend:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

Frontend:

```powershell
cd frontend
npm run lint
npm run build
```

If PowerShell blocks `npm.ps1`, use:

```powershell
npm.cmd run lint
npm.cmd run build
```

## Runtime Data And Generated Files

Do not commit runtime/generated files:

- `backend/.venv/`
- `backend/.pytest_cache/`
- `backend/data/`
- `frontend/node_modules/`
- `frontend/.next/`

SQLite blog storage and ChromaDB data are created under `backend/data/` by default.
Brand Voice SFT/DPO datasets are also generated under `backend/data/brand_voice/` by default.

## Configuration Notes

- Start from `backend/.env.example`, then copy it to `backend/.env`.
- `DEBUG` must be a valid boolean such as `true` or `false`.
- Web Search requires `SERPER_API_KEY`.
- RAG uses ChromaDB and documents uploaded from the `/rag` page.
- Brand Voice Profile defaults:
  - `BRAND_VOICE_PROFILE_PATH=./config/brand_voice_profile.json`
  - `BRAND_VOICE_DATASET_DIR=./data/brand_voice`
