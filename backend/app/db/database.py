import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Iterator

from app.core.config import get_settings
from app.core.logging import logger


SCHEMA_VERSION = 5


def get_db_path() -> Path:
    settings = get_settings()
    data_dir = Path(settings.CHROMA_PERSIST_DIR).parent
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "blog_os.db"


@contextmanager
def get_connection(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path or get_db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        yield conn
    finally:
        conn.close()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _ensure_column(conn: sqlite3.Connection, table: str, name: str, definition: str) -> None:
    if name not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _migration_1(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS blogs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            seo_title TEXT,
            meta_description TEXT,
            content TEXT NOT NULL,
            keywords TEXT,
            status TEXT DEFAULT 'draft',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS brand_voice_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id TEXT NOT NULL,
            blog_id INTEGER,
            channel TEXT NOT NULL,
            content_type TEXT NOT NULL,
            persona_name TEXT,
            content_preview TEXT NOT NULL,
            automated_score INTEGER NOT NULL,
            evaluation_json TEXT NOT NULL,
            human_score INTEGER,
            human_notes TEXT,
            approved INTEGER DEFAULT 0,
            reviewer TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS documents (
            document_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL DEFAULT 'default',
            profile_id TEXT,
            filename TEXT NOT NULL,
            source_url TEXT,
            extension TEXT NOT NULL,
            purpose TEXT NOT NULL DEFAULT 'knowledge',
            cluster TEXT NOT NULL DEFAULT 'knowledge',
            category TEXT,
            human_rating INTEGER,
            dataset_split TEXT,
            total_chunks INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'indexed',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(project_id)
        );

        CREATE TABLE IF NOT EXISTS brand_voice_profiles (
            profile_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            name TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            is_active INTEGER NOT NULL DEFAULT 0,
            source_document_ids_json TEXT NOT NULL DEFAULT '[]',
            profile_json TEXT NOT NULL,
            metrics_json TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(project_id)
        );

        CREATE TABLE IF NOT EXISTS evaluation_runs (
            run_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            dataset_name TEXT NOT NULL,
            split_strategy TEXT NOT NULL,
            seed INTEGER NOT NULL DEFAULT 42,
            status TEXT NOT NULL DEFAULT 'pending',
            metrics_json TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS evaluation_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            source_document_id TEXT,
            category TEXT,
            topic TEXT NOT NULL,
            generated_content TEXT,
            human_rating INTEGER,
            automated_score INTEGER,
            dimension_scores_json TEXT NOT NULL DEFAULT '{}',
            violations_json TEXT NOT NULL DEFAULT '[]',
            recommendations_json TEXT NOT NULL DEFAULT '[]',
            passed INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


def _migration_2(conn: sqlite3.Connection) -> None:
    for name, definition in {
        "seo_title": "TEXT",
        "meta_description": "TEXT",
        "keywords": "TEXT",
        "project_id": "TEXT NOT NULL DEFAULT 'default'",
        "generation_run_id": "TEXT",
        "approved_by": "TEXT",
        "approved_at": "TIMESTAMP",
    }.items():
        _ensure_column(conn, "blogs", name, definition)

    _ensure_column(conn, "documents", "approval_status", "TEXT NOT NULL DEFAULT 'pending'")
    _ensure_column(conn, "brand_voice_profiles", "status", "TEXT NOT NULL DEFAULT 'draft'")
    _ensure_column(conn, "brand_voice_profiles", "activated_at", "TIMESTAMP")
    _ensure_column(conn, "brand_voice_profiles", "artifact_path", "TEXT")

    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_documents_scope
            ON documents(project_id, cluster, profile_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_profile_version
            ON brand_voice_profiles(project_id, name, version);
        CREATE INDEX IF NOT EXISTS idx_profile_active
            ON brand_voice_profiles(project_id, is_active);

        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            job_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            payload_json TEXT NOT NULL DEFAULT '{}',
            result_json TEXT,
            error_json TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 2,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(project_id)
        );

        CREATE TABLE IF NOT EXISTS generation_runs (
            run_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            profile_id TEXT,
            profile_version INTEGER,
            status TEXT NOT NULL DEFAULT 'planning',
            brief_json TEXT NOT NULL,
            outline_json TEXT NOT NULL DEFAULT '[]',
            final_content TEXT,
            title_tag TEXT,
            meta_description TEXT,
            quality_report_json TEXT NOT NULL DEFAULT '{}',
            rewrite_count INTEGER NOT NULL DEFAULT 0,
            created_by TEXT,
            reviewed_by TEXT,
            reviewed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(project_id)
        );

        CREATE TABLE IF NOT EXISTS generation_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            attempt_number INTEGER NOT NULL,
            content TEXT NOT NULL,
            quality_report_json TEXT NOT NULL DEFAULT '{}',
            model_name TEXT,
            prompt_version TEXT,
            duration_seconds REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(run_id, attempt_number),
            FOREIGN KEY (run_id) REFERENCES generation_runs(run_id)
        );

        CREATE TABLE IF NOT EXISTS generation_citations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            chunk_index INTEGER,
            source_url TEXT,
            excerpt TEXT NOT NULL,
            relevance_score REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (run_id) REFERENCES generation_runs(run_id)
        );
        """
    )


def _migration_3(conn: sqlite3.Connection) -> None:
    _ensure_column(conn, "jobs", "idempotency_key", "TEXT")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_idempotency "
        "ON jobs(project_id, idempotency_key) WHERE idempotency_key IS NOT NULL"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_claim ON jobs(status, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_generation_project ON generation_runs(project_id, created_at)")


def _migration_4(conn: sqlite3.Connection) -> None:
    _ensure_column(conn, "generation_runs", "human_score", "INTEGER")
    _ensure_column(conn, "generation_runs", "review_notes", "TEXT")
    _ensure_column(conn, "generation_runs", "edited_content", "TEXT")


def _migration_5(conn: sqlite3.Connection) -> None:
    _ensure_column(conn, "generation_runs", "planned_title", "TEXT")
    _ensure_column(conn, "generation_runs", "planned_seo_title", "TEXT")


def init_db(db_path: Path | None = None) -> None:
    db_path = db_path or get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Initializing SQLite database at {}", db_path)

    with get_connection(db_path) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
        migrations = (
            (1, _migration_1),
            (2, _migration_2),
            (3, _migration_3),
            (4, _migration_4),
            (5, _migration_5),
        )
        for version, migration in migrations:
            if version not in applied:
                migration(conn)
                conn.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
        conn.execute(
            "INSERT OR IGNORE INTO projects(project_id, name) VALUES (?, ?)",
            ("default", "Default project"),
        )
        conn.commit()


def get_db() -> Generator[sqlite3.Connection, None, None]:
    with get_connection() as conn:
        yield conn
