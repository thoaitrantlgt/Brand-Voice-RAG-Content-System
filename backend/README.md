# 🤖 AI Content OS — Backend

> **Hệ thống tự động hóa sản xuất nội dung Blog sử dụng kiến trúc Multi-Agent AI.**
> Xây dựng trên FastAPI + CrewAI, hỗ trợ Hybrid Inference (Cloud & Local) và RAG Knowledge Hub.

---

## 📋 Mục Lục

- [Tổng Quan](#tổng-quan)
- [Tech Stack](#tech-stack)
- [Kiến Trúc](#kiến-trúc)
- [Yêu Cầu Hệ Thống](#yêu-cầu-hệ-thống)
- [Cài Đặt](#cài-đặt)
- [Cấu Hình](#cấu-hình)
- [Chạy Server](#chạy-server)
- [API Endpoints](#api-endpoints)
- [Chạy Tests](#chạy-tests)
- [Roadmap](#roadmap)

---

## Tổng Quan

AI Content OS là backend cho một **Content Generation Pipeline** 3 bước hoàn toàn tự động:

```
Keywords
       │
       ▼
┌─────────────────┐
│  Planner Agent  │  → Phân tích từ khóa, tạo tiêu đề + outline
│ (Strategist)    │
└────────┬────────┘
         │ [Human Review: chọn tiêu đề]
         ▼
┌─────────────────┐
│  Writer Agent   │  → Viết bài chi tiết (có RAG từ Knowledge Hub)
│ (Copywriter)    │
└────────┬────────┘
         ▼
┌─────────────────┐
│  Editor Agent   │  → Tối ưu SEO On-page, title tag, meta description
│ (SEO Specialist)│
└────────┬────────┘
         ▼
  Optimized Blog Post ✅
```

---

## Tech Stack

| Thành Phần | Công Nghệ |
|:-----------|:----------|
| **Web Framework** | FastAPI 0.115+ |
| **AI Orchestration** | CrewAI 0.80+ |
| **LLM Providers** | Google Gemini, OpenAI GPT-4o, Anthropic Claude, HuggingFace, Ollama |
| **RAG — Document Loader** | LangChain Community |
| **RAG — Vector DB** | ChromaDB (persistent, on-disk) |
| **RAG — Embeddings** | sentence-transformers (default, local & free) |
| **Validation** | Pydantic v2 + pydantic-settings |
| **Logging** | Loguru |
| **Testing** | Pytest + pytest-asyncio |

---

## Kiến Trúc

Dự án được thiết kế theo nguyên tắc **SOLID**, tổ chức theo kiến trúc phân lớp rõ ràng:

```
backend/
├── app/
│   ├── main.py                   # FastAPI app factory
│   │
│   ├── core/                     # 🧱 Infrastructure Layer
│   │   ├── config.py             # Centralized settings (pydantic-settings)
│   │   ├── exceptions.py         # Domain custom exceptions
│   │   ├── logging.py            # Loguru setup
│   │   └── interfaces/           # Abstract contracts (ABC)
│   │       ├── base_agent.py     # IAgent
│   │       ├── base_task.py      # ITask
│   │       ├── base_tool.py      # ITool
│   │       ├── base_crew.py      # ICrew
│   │       ├── base_vector_store.py      # IVectorStore
│   │       └── base_document_processor.py # IDocumentProcessor
│   │
│   ├── agents/                   # 🤖 CrewAI Agents
│   │   ├── llm_factory.py        # LLM Factory (5 providers)
│   │   ├── planner_agent.py      # Content Strategist
│   │   ├── writer_agent.py       # Expert Copywriter
│   │   └── editor_agent.py       # SEO Specialist
│   │
│   ├── tasks/                    # 📋 Task Definitions
│   │   ├── planner_task.py
│   │   ├── writer_task.py
│   │   └── editor_task.py
│   │
│   ├── tools/                    # 🔧 Custom Agent Tools
│   │   ├── web_search_tool.py    # Tavily Search
│   │   ├── rss_reader_tool.py    # RSS Feed Reader
│   │   └── knowledge_base_tool.py # ChromaDB RAG Tool
│   │
│   ├── rag/                      # 📚 RAG Knowledge Hub
│   │   ├── document_processor.py # LangChain Loader + Splitter
│   │   ├── embeddings_factory.py # Embedding model factory
│   │   ├── vector_store.py       # ChromaDB implementation
│   │   └── retrieval_engine.py   # Semantic retrieval
│   │
│   ├── crews/                    # 🎬 Orchestration
│   │   └── content_crew.py       # Sequential: Planner→Writer→Editor
│   │
│   ├── services/                 # ⚙️ Business Logic
│   │   ├── content_service.py
│   │   └── document_service.py
│   │
│   ├── schemas/                  # 📦 Pydantic Models
│   │   ├── content.py
│   │   └── document.py
│   │
│   └── api/v1/                   # 🌐 FastAPI Routers
│       ├── content_router.py
│       └── document_router.py
│
├── tests/
├── .env.example
├── requirements.txt
└── run.py
```

---

## Yêu Cầu Hệ Thống

- **Python** 3.12+
- **pip** hoặc **uv**
- *(Tuỳ chọn)* [Ollama](https://ollama.com/) nếu chạy Local mode
- *(Tuỳ chọn)* GPU + CUDA nếu chạy HuggingFace Local pipeline

---

## Cài Đặt

### 1. Clone và tạo virtual environment

```bash
git clone <repository-url>
cd blog/backend

python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 2. Cài dependencies

```bash
pip install -r requirements.txt
```

> **Lưu ý:** `sentence-transformers` (~500MB) sẽ download model embedding lần đầu chạy.
> Các lần sau được cache tự động.

### 3. Cấu hình môi trường

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Mở `.env` và điền API keys cần thiết (xem phần [Cấu Hình](#cấu-hình) bên dưới).

---

## Cấu Hình

### Chọn AI Provider

Chỉnh `RUN_MODE` và `AI_PROVIDER` trong file `.env`:

| Kịch bản | Config |
|:---------|:-------|
| **Cloud — Google Gemini** (khuyến nghị) | `RUN_MODE=cloud` + `AI_PROVIDER=google` |
| **Cloud — OpenAI GPT** | `RUN_MODE=cloud` + `AI_PROVIDER=openai` |
| **Cloud — Anthropic Claude** | `RUN_MODE=cloud` + `AI_PROVIDER=anthropic` |
| **Cloud — HuggingFace API** | `RUN_MODE=cloud` + `AI_PROVIDER=huggingface` |
| **Local — Ollama** | `RUN_MODE=local` + `AI_PROVIDER=ollama` |
| **Local — HuggingFace pipeline** | `RUN_MODE=local` + `AI_PROVIDER=huggingface` |

### Chọn Embedding Model (RAG)

| Provider | Model | Yêu cầu |
|:---------|:------|:---------|
| `huggingface` *(default)* | `all-MiniLM-L6-v2` | Không cần API key, chạy local CPU |
| `google` | `text-embedding-004` | `GOOGLE_API_KEY` |
| `openai` | `text-embedding-3-small` | `OPENAI_API_KEY` |

### API Keys tối thiểu cần thiết

```env
# Chọn ít nhất 1 trong các keys sau tuỳ provider bạn dùng:
GOOGLE_API_KEY=...
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
HUGGINGFACE_API_KEY=...

# Cho Planner Agent tìm kiếm web (cần 1 trong 2):
TAVILY_API_KEY=...
```

> **Chạy hoàn toàn miễn phí:** Dùng `EMBEDDING_PROVIDER=huggingface` (không cần API key)
> + Ollama local cho LLM.

---

## Chạy Server

```bash
# Development (auto-reload)
python run.py

# Hoặc dùng uvicorn trực tiếp
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Server sẽ chạy tại: **http://localhost:8000**

| URL | Mô tả |
|:----|:------|
| `http://localhost:8000/docs` | Swagger UI — thử API trực tiếp |
| `http://localhost:8000/redoc` | ReDoc documentation |
| `http://localhost:8000/health` | Health check |

---

## API Endpoints

### Content Generation

| Method | Endpoint | Mô tả |
|:-------|:---------|:------|
| `POST` | `/api/v1/content/titles` | **Bước 1:** Planner phân tích từ khóa → tạo danh sách tiêu đề |
| `POST` | `/api/v1/content/generate` | **Bước 2:** Writer + Editor → bài viết tối ưu SEO hoàn chỉnh |

**Ví dụ Bước 1:**
```bash
curl -X POST http://localhost:8000/api/v1/content/titles \
  -H "Content-Type: application/json" \
  -d '{
    "keywords": ["AI writing tool", "content automation"],
    "use_web_search": true
  }'
```

**Ví dụ Bước 2:**
```bash
curl -X POST http://localhost:8000/api/v1/content/generate \
  -H "Content-Type: application/json" \
  -d '{
    "keywords": ["AI writing tool"],
    "selected_title": "10 cách dùng AI để viết blog nhanh hơn 10x"
  }'
```

### Knowledge Hub (RAG)

| Method | Endpoint | Mô tả |
|:-------|:---------|:------|
| `POST` | `/api/v1/documents/upload` | Upload tài liệu (PDF/TXT/MD/DOCX) → tự động chunk + index |
| `GET` | `/api/v1/documents` | Danh sách tài liệu đã index |
| `DELETE` | `/api/v1/documents/{id}` | Xóa tài liệu khỏi Knowledge Hub |
| `POST` | `/api/v1/documents/search` | Semantic search trong Knowledge Hub |

**Upload tài liệu:**
```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -F "file=@/path/to/document.pdf"
```

**Tìm kiếm:**
```bash
curl -X POST http://localhost:8000/api/v1/documents/search \
  -H "Content-Type: application/json" \
  -d '{"query": "best practices for REST API", "top_k": 5}'
```

---

## Chạy Tests

```bash
# Chạy tất cả tests
pytest

# Chạy với output chi tiết
pytest -v

# Chạy riêng test RAG
pytest tests/test_rag.py -v

# Chạy với coverage report
pytest --cov=app tests/
```

> Tests dùng **mock** hoàn toàn — không cần API keys hay ChromaDB thật khi test.

---

## Roadmap

| Phase | Trạng thái | Nội dung |
|:------|:----------:|:---------|
| **Phase 1** — Core Pipeline | ✅ Hoàn thành | FastAPI + CrewAI (Planner→Writer→Editor), LLM Factory |
| **Phase 2** — Hybrid Model & RAG | ✅ Hoàn thành | HuggingFace support, ChromaDB, Document Upload API |
| **Phase 3** — Frontend & HITL | 🔜 Sắp tới | Next.js Dashboard, Inline Comment AI Re-write |
| **Phase 4** — Publishing Pipeline | 🔜 Sắp tới | WordPress API, Social Media, Email, Telegram |

---

## Đóng Góp

1. Fork repository
2. Tạo branch mới: `git checkout -b feature/ten-tinh-nang`
3. Commit: `git commit -m "feat: mô tả thay đổi"`
4. Push và tạo Pull Request

---

## License

MIT License — xem file [LICENSE](LICENSE) để biết thêm chi tiết.
