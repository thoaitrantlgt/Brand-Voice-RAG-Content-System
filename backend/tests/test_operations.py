import json
import sqlite3

import httpx

from app.core.config import Settings
from app.db.database import init_db
from app.services.readiness_service import ReadinessService
from scripts.backup_runtime import backup_runtime, restore_runtime


def test_readiness_requires_database_storage_and_expected_model(tmp_path):
    chroma = tmp_path / "data" / "chroma"
    chroma.mkdir(parents=True)
    init_db(tmp_path / "data" / "blog_os.db")
    settings = Settings(
        CHROMA_PERSIST_DIR=str(chroma),
        OPENAI_API_BASE="http://lm-studio.test/v1",
        WRITER_MODEL="qwen3.5-2b",
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"data": [{"id": "qwen3.5-2b"}]})
    )

    result = ReadinessService(settings, httpx.Client(transport=transport)).check()

    assert result["ready"] is True
    assert all(check["ok"] for check in result["checks"].values())


def test_readiness_fails_when_loaded_model_does_not_match(tmp_path):
    chroma = tmp_path / "data" / "chroma"
    chroma.mkdir(parents=True)
    init_db(tmp_path / "data" / "blog_os.db")
    settings = Settings(
        CHROMA_PERSIST_DIR=str(chroma),
        OPENAI_API_BASE="http://lm-studio.test/v1",
        WRITER_MODEL="qwen3.5-2b",
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"data": [{"id": "another-model"}]})
    )

    result = ReadinessService(settings, httpx.Client(transport=transport)).check()

    assert result["ready"] is False
    assert result["checks"]["model"]["ok"] is False


def test_runtime_backup_and_restore_preserve_database_and_artifacts(tmp_path):
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"
    backup_dir = tmp_path / "backup"
    restored_data = tmp_path / "restored-data"
    restored_config = tmp_path / "restored-config"
    data_dir.mkdir()
    config_dir.mkdir()
    init_db(data_dir / "blog_os.db")
    with sqlite3.connect(data_dir / "blog_os.db") as conn:
        conn.execute("INSERT INTO projects(project_id, name) VALUES ('alpha', 'Alpha')")
    (data_dir / "uploads").mkdir()
    (data_dir / "uploads" / "source.md").write_text("source", encoding="utf-8")
    (config_dir / "corporate_style_guide.json").write_text("{}", encoding="utf-8")

    manifest = backup_runtime(data_dir, config_dir, backup_dir)
    restore_runtime(backup_dir, restored_data, restored_config)

    with sqlite3.connect(restored_data / "blog_os.db") as conn:
        project = conn.execute("SELECT name FROM projects WHERE project_id = 'alpha'").fetchone()
    assert project[0] == "Alpha"
    assert (restored_data / "uploads" / "source.md").read_text(encoding="utf-8") == "source"
    assert json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))["version"] == 1
    assert manifest["version"] == 1
