"""Index the prepared TSS train split into isolated Chroma clusters."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings  # noqa: E402
from app.db.database import init_db  # noqa: E402
from app.rag.vector_store import ChromaVectorStore  # noqa: E402
from app.repositories.document_repository import DocumentRepository  # noqa: E402


def chunk_text(text: str, max_chars: int = 1600) -> list[str]:
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) + 2 > max_chars:
            chunks.append(current)
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}".strip()
    if current:
        chunks.append(current)
    return chunks


def index_document(
    store: ChromaVectorStore,
    repository: DocumentRepository,
    project_id: str,
    profile_id: str,
    record: dict[str, Any],
    article: dict[str, str],
    cluster: str,
) -> int:
    document_id = f"{project_id}-{record['stt']}-{cluster}"
    title = article.get("title") or f"TSS article {record['stt']}"
    chunks = chunk_text(f"# {title}\n\n{article.get('text', '')}")
    if not chunks:
        return 0

    store.delete_document(document_id)
    repository.delete(document_id)
    metadatas = [
        {
            "document_id": document_id,
            "project_id": project_id,
            "profile_id": profile_id,
            "cluster": cluster,
            "purpose": cluster,
            "filename": f"tss-{record['stt']}.html",
            "source_url": record["link"],
            "category": record["category"],
            "human_rating": record["rating"],
            "dataset_split": "train",
            "chunk_index": index,
        }
        for index in range(len(chunks))
    ]
    store.add_documents(
        texts=chunks,
        metadatas=metadatas,
        ids=[f"{document_id}_{index}" for index in range(len(chunks))],
    )
    repository.create(
        {
            "document_id": document_id,
            "project_id": project_id,
            "profile_id": profile_id,
            "filename": f"tss-{record['stt']}.html",
            "source_url": record["link"],
            "extension": "html",
            "purpose": cluster,
            "cluster": cluster,
            "category": record["category"],
            "human_rating": record["rating"],
            "dataset_split": "train",
            "total_chunks": len(chunks),
            "status": "indexed",
            "metadata": {"dataset": "tss_sheet"},
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return len(chunks)


def run(dataset_dir: Path, project_id: str) -> dict[str, int]:
    split = json.loads((dataset_dir / "split_manifest.json").read_text(encoding="utf-8"))
    articles = json.loads((dataset_dir / "article_texts.json").read_text(encoding="utf-8"))
    profile = json.loads((dataset_dir / "brand_voice_profile.json").read_text(encoding="utf-8"))
    profile_id = str(profile["profile_id"])

    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    init_db()
    repository = DocumentRepository()
    store = ChromaVectorStore(Settings())
    totals = {"knowledge_documents": 0, "knowledge_chunks": 0, "brand_voice_documents": 0, "brand_voice_chunks": 0}

    for record in split["train"]:
        article = articles.get(record["link"], {})
        count = index_document(store, repository, project_id, profile_id, record, article, "knowledge")
        if count:
            totals["knowledge_documents"] += 1
            totals["knowledge_chunks"] += count
        if int(record["rating"]) >= 4:
            count = index_document(store, repository, project_id, profile_id, record, article, "brand_voice")
            if count:
                totals["brand_voice_documents"] += 1
                totals["brand_voice_chunks"] += count
    return totals


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=Path("data/eval/tss_pipeline_v2"))
    parser.add_argument("--project", default="tss")
    args = parser.parse_args()
    print(json.dumps(run(args.dataset_dir, args.project), ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
