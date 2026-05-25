# AI Content Blog OS

Ứng dụng tạo và quản lý bài viết blog bằng Multi-Agent AI. Dự án gồm backend FastAPI để xử lý AI/RAG/blog storage và frontend Next.js để thao tác dashboard, tạo bài, quản lý bài viết, upload tài liệu.

## Tính năng chính

- Dashboard hiển thị dữ liệu thật từ backend: số bài viết, bản nháp, bài đã xuất bản, tài liệu RAG và tình trạng hệ thống.
- Tạo bài viết theo luồng: nhập từ khóa -> AI nghiên cứu web/tài liệu upload -> tạo draft outline -> người dùng feedback -> Writer + Editor viết bài hoàn chỉnh.
- Upload tài liệu PDF/TXT/MD/DOCX vào Knowledge Hub để AI tham khảo khi lập draft hoặc viết bài.
- Quản lý bài viết: xem, sửa, xóa, lưu nháp hoặc xuất bản.
- Inline AI rewrite: chọn đoạn văn và yêu cầu AI viết lại theo feedback.

## Cấu trúc thư mục

```text
.
├── backend/   # FastAPI, CrewAI, RAG, SQLite blog storage
├── frontend/  # Next.js, React, Tailwind CSS
├── AGENTS.md  # Ghi chú vận hành repo cho coding agents
└── README.md
```

Không có root task runner. Khi chạy lệnh, hãy vào đúng thư mục `backend/` hoặc `frontend/`.

## Yêu cầu

- Python 3.12+
- Node.js + npm
- API key/model provider phù hợp với cấu hình backend
- Tùy chọn: `SERPER_API_KEY` nếu muốn bật Web Search

## Chạy backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
.\.venv\Scripts\python.exe run.py
```

Backend mặc định chạy tại:

```text
http://127.0.0.1:8000
```

Các route chính:

- `GET /health`
- `POST /api/v1/content/titles` - tạo draft outline từ từ khóa
- `POST /api/v1/content/generate` - viết bài hoàn chỉnh từ draft đã duyệt
- `POST /api/v1/content/rewrite` - viết lại đoạn được chọn
- `GET/POST/PUT/DELETE /api/v1/blogs`
- `GET/POST/DELETE /api/v1/documents`

Lưu ý: backend đọc `.env` theo current working directory, nên hãy chạy lệnh từ thư mục `backend/`.

## Chạy frontend

```powershell
cd frontend
npm install
npm run dev
```

Frontend mặc định chạy tại:

```text
http://127.0.0.1:3000
```

Các trang chính:

- `/` - Dashboard
- `/create` - Tạo bài viết
- `/blogs` - Quản lý bài viết
- `/rag` - Upload và tìm kiếm tài liệu

Frontend hiện gọi backend tại `http://127.0.0.1:8000/api/v1`.

## Luồng tạo bài viết

1. Vào `/create`.
2. Nhập từ khóa chính, có thể tách nhiều từ khóa bằng dấu phẩy.
3. Bật Web Search nếu muốn AI cập nhật thông tin từ web.
4. Planner Agent tìm thông tin từ web hoặc tài liệu đã upload trong Knowledge Hub.
5. Hệ thống tạo một draft gồm tiêu đề, SEO title, đề mục và gạch đầu dòng.
6. Người dùng chỉnh draft/outline.
7. Writer + Editor Agent viết bài hoàn chỉnh.
8. Người dùng có thể preview, chỉnh markdown, rewrite từng đoạn, lưu nháp hoặc xuất bản.

## Kiểm thử

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

Nếu PowerShell chặn `npm.ps1`, dùng:

```powershell
npm.cmd run lint
npm.cmd run build
```

## Dữ liệu và file generated

Các thư mục/file runtime không nên commit:

- `backend/.venv/`
- `backend/.pytest_cache/`
- `backend/data/`
- `frontend/node_modules/`
- `frontend/.next/`

SQLite blog storage và ChromaDB mặc định được tạo dưới `backend/data/`.

## Ghi chú cấu hình

- Bắt đầu từ `backend/.env.example`, copy sang `backend/.env`.
- `DEBUG` cần là boolean hợp lệ như `true` hoặc `false`.
- Web Search cần `SERPER_API_KEY`.
- RAG dùng ChromaDB và tài liệu upload từ trang `/rag`.
