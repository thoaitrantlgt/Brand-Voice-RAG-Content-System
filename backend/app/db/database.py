import sqlite3
from pathlib import Path
from typing import Generator
from app.core.config import get_settings
from app.core.logging import logger

def get_db_path() -> Path:
    settings = get_settings()
    data_dir = Path(settings.CHROMA_PERSIST_DIR).parent
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "blog_os.db"

def init_db():
    """Khởi tạo database và tạo table nếu chưa có."""
    db_path = get_db_path()
    logger.info("Initializing SQLite database at {}", db_path)
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
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
            )
        """)
        cursor.execute("""
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
            )
        """)
        conn.commit()

def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Dependency cho FastAPI để lấy DB connection."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row  # Trả về dict-like object
    try:
        yield conn
    finally:
        conn.close()
