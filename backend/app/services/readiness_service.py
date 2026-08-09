import sqlite3
from pathlib import Path
from typing import Any

import httpx

from app.core.config import AIProvider, RunMode, Settings


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
        if (
            self.settings.RUN_MODE == RunMode.CLOUD
            and self.settings.AI_PROVIDER == AIProvider.GOOGLE
        ):
            api_key = self.settings.GOOGLE_API_KEY.strip()
            ok = bool(api_key) and not api_key.lower().startswith(("your_", "replace-"))
            return {
                "ok": ok,
                "provider": AIProvider.GOOGLE.value,
                "expected": self.settings.WRITER_MODEL,
                "error": None if ok else "GOOGLE_API_KEY is not configured",
            }

        provider = self.settings.AI_PROVIDER
        if provider == AIProvider.VLLM:
            base_url = self.settings.VLLM_BASE_URL
            api_key = self.settings.VLLM_API_KEY
        else:
            base_url = self.settings.OPENAI_API_BASE
            api_key = self.settings.OPENAI_API_KEY
        if not base_url:
            setting = "VLLM_BASE_URL" if provider == AIProvider.VLLM else "OPENAI_API_BASE"
            return {"ok": False, "provider": provider.value, "error": f"{setting} is not configured"}
        url = f"{base_url.rstrip('/')}/models"
        try:
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
            response = self.client.get(url, headers=headers)
            response.raise_for_status()
            model_ids = [str(item.get("id", "")) for item in response.json().get("data", [])]
            expected = self.settings.WRITER_MODEL
            ok = expected in model_ids
            return {
                "ok": ok,
                "provider": provider.value,
                "expected": expected,
                "loaded": model_ids,
                "error": None if ok else "Expected model is not loaded",
            }
        except Exception as exc:
            return {
                "ok": False,
                "provider": provider.value,
                "expected": self.settings.WRITER_MODEL,
                "error": str(exc),
            }
