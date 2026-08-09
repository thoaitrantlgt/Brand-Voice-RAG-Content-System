import json
import sqlite3

import pytest

from app.core.auth import AuthError, Principal, parse_token_registry, require_role
from app.db.database import get_connection, init_db
from app.repositories.brand_voice_profile_repository import BrandVoiceProfileRepository
from app.core.config import Settings


def test_init_db_migrates_existing_blog_rows_without_data_loss(tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE blogs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                status TEXT DEFAULT 'draft',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute("INSERT INTO blogs(title, content) VALUES ('Kept', 'Body')")

    init_db(db_path)

    with get_connection(db_path) as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(blogs)")}
        row = conn.execute("SELECT title, project_id, status FROM blogs").fetchone()
        versions = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        retrieval_table = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name = 'generation_retrieval_contexts'"
        ).fetchone()
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]

    assert {"project_id", "generation_run_id", "approved_by", "approved_at"} <= columns
    assert dict(row) == {"title": "Kept", "project_id": "default", "status": "draft"}
    assert [item[0] for item in versions] == [1, 2, 3, 4, 5, 6]
    assert retrieval_table["name"] == "generation_retrieval_contexts"
    assert journal_mode.lower() == "wal"


def test_profile_versions_and_activation_are_isolated_by_project(tmp_path):
    db_path = tmp_path / "profiles.db"
    init_db(db_path)
    repository = BrandVoiceProfileRepository(db_path)

    first = repository.create("alpha", "Main", {"tone": "direct"}, ["doc-1"])
    second = repository.create("alpha", "Main", {"tone": "warm"}, ["doc-2"])
    other = repository.create("beta", "Main", {"tone": "formal"}, ["doc-3"])

    repository.activate("alpha", second["profile_id"])
    repository.activate("beta", other["profile_id"])

    assert first["version"] == 1
    assert second["version"] == 2
    assert repository.get_active("alpha")["profile_id"] == second["profile_id"]
    assert repository.get_active("beta")["profile_id"] == other["profile_id"]
    assert repository.get("alpha", first["profile_id"])["status"] == "archived"
    assert repository.get("beta", second["profile_id"]) is None


def test_token_registry_resolves_roles_and_rejects_insufficient_access():
    registry = parse_token_registry(
        json.dumps(
            {
                "writer-token": {"username": "An", "role": "writer", "projects": ["alpha"]},
                "review-token": {"username": "Binh", "role": "reviewer", "projects": ["alpha", "beta"]},
            }
        )
    )

    assert registry["writer-token"] == Principal(username="An", role="writer", projects=frozenset({"alpha"}))
    assert require_role(registry["review-token"], "reviewer").username == "Binh"
    with pytest.raises(AuthError, match="reviewer role required"):
        require_role(registry["writer-token"], "reviewer")


def test_secure_defaults_disable_legacy_and_insecure_auth():
    assert Settings.model_fields["ENABLE_LEGACY_SYNC_API"].default is False
    assert Settings.model_fields["ALLOW_INSECURE_AUTH"].default is False
