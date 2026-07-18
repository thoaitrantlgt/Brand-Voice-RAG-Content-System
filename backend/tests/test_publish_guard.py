import sqlite3

import pytest

from app.db.database import get_connection, init_db
from app.repositories.blog_repository import BlogRepository
from app.repositories.generation_repository import GenerationRunRepository
from app.schemas.blog import BlogCreate, BlogUpdate


def test_blog_cannot_be_created_as_published_without_approved_run(tmp_path):
    db_path = tmp_path / "publish.db"
    init_db(db_path)
    with get_connection(db_path) as conn:
        repository = BlogRepository(conn)
        with pytest.raises(ValueError, match="approved generation run"):
            repository.create(
                BlogCreate(title="Bypass", content="Body", status="published", project_id="alpha")
            )


def test_approved_generation_can_create_published_blog(tmp_path):
    db_path = tmp_path / "publish.db"
    init_db(db_path)
    runs = GenerationRunRepository(db_path)
    run = runs.create("alpha", {"topic": "Topic", "keywords": ["topic"]}, "An")
    runs.set_plan(run["run_id"], "Approved title", "SEO title", ["## Intro"])
    runs.begin_generation(run["run_id"])
    runs.record_attempt(run["run_id"], "# Approved title\n\nBody", {"passed": True}, "qwen")
    runs.finalize(run["run_id"], "# Approved title\n\nBody", {"passed": True}, 0)
    runs.review(run["run_id"], "Binh", True, human_score=90)

    with get_connection(db_path) as conn:
        repository = BlogRepository(conn)
        blog_id = repository.create(
            BlogCreate(
                title="Approved title",
                content="# Approved title\n\nBody",
                status="published",
                project_id="alpha",
                generation_run_id=run["run_id"],
            )
        )
        saved = repository.get_by_id(blog_id)

    assert saved["status"] == "published"
    assert saved["generation_run_id"] == run["run_id"]


def test_approved_run_cannot_publish_different_content_or_project(tmp_path):
    db_path = tmp_path / "publish.db"
    init_db(db_path)
    runs = GenerationRunRepository(db_path)
    run = runs.create("alpha", {"topic": "Topic", "keywords": ["topic"]}, "An")
    runs.set_plan(run["run_id"], "Approved title", "SEO title", ["## Intro"])
    runs.begin_generation(run["run_id"])
    runs.record_attempt(run["run_id"], "# Approved title\n\nBody", {"passed": True}, "qwen")
    runs.finalize(run["run_id"], "# Approved title\n\nBody", {"passed": True}, 0)
    runs.review(run["run_id"], "Binh", True, human_score=90)

    with get_connection(db_path) as conn:
        repository = BlogRepository(conn)
        with pytest.raises(ValueError, match="match the approved generation run"):
            repository.create(BlogCreate(title="Approved title", content="Injected", status="published", project_id="alpha", generation_run_id=run["run_id"]))
        with pytest.raises(ValueError, match="match the approved generation run"):
            repository.create(BlogCreate(title="Approved title", content="# Approved title\n\nBody", status="published", project_id="beta", generation_run_id=run["run_id"]))


def test_published_blog_is_immutable(tmp_path):
    db_path = tmp_path / "publish.db"
    init_db(db_path)
    runs = GenerationRunRepository(db_path)
    run = runs.create("alpha", {"topic": "Topic", "keywords": []}, "An")
    runs.set_plan(run["run_id"], "Title", "Title", ["## Intro"])
    runs.begin_generation(run["run_id"])
    runs.record_attempt(run["run_id"], "Body", {"passed": True}, "qwen")
    runs.finalize(run["run_id"], "Body", {"passed": True}, 0)
    runs.review(run["run_id"], "Binh", True)
    published = runs.publish(run["run_id"])
    with get_connection(db_path) as conn:
        repository = BlogRepository(conn)
        with pytest.raises(ValueError, match="immutable"):
            repository.update(published["blog_id"], BlogUpdate(content="Changed"))
        with pytest.raises(ValueError, match="immutable"):
            repository.delete(published["blog_id"])
