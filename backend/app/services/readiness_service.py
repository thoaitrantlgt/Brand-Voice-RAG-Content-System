import sqlite3
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings


class ReadinessService:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self.client = client or httpx.Client(timeout=2.0)

    def check(self) -> dict[str, Any]:
        checks = {
            "database": self._check_database(),
            "vector_storage": self._check_vector_storage(),
            "model": self._check_model(),
        }
        return {"ready": all(item["ok"] for item in checks.values()), "checks": checks}

    def _check_database(self) -> dict[str, Any]:
        db_path = Path(self.settings.CHROMA_PERSIST_DIR).parent / "blog_os.db"
        try:
            with sqlite3.connect(db_path, timeout=2) as conn:
                conn.execute("SELECT 1").fetchone()
            return {"ok": True, "path": str(db_path)}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "path": str(db_path)}

    def _check_vector_storage(self) -> dict[str, Any]:
        path = Path(self.settings.CHROMA_PERSIST_DIR)
        ok = path.exists() and path.is_dir()
        return {"ok": ok, "path": str(path), "error": None if ok else "Storage directory missing"}

    def _check_model(self) -> dict[str, Any]:
        if not self.settings.OPENAI_API_BASE:
            return {"ok": False, "error": "OPENAI_API_BASE is not configured"}
        url = f"{self.settings.OPENAI_API_BASE.rstrip('/')}/models"
        try:
            response = self.client.get(url)
            response.raise_for_status()
            model_ids = [str(item.get("id", "")) for item in response.json().get("data", [])]
            expected = self.settings.WRITER_MODEL
            ok = expected in model_ids
            return {
                "ok": ok,
                "expected": expected,
                "loaded": model_ids,
                "error": None if ok else "Expected model is not loaded",
            }
        except Exception as exc:
            return {"ok": False, "expected": self.settings.WRITER_MODEL, "error": str(exc)}
