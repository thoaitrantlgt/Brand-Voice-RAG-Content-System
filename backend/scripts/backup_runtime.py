import argparse
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKUP_DIRS = ("chroma", "uploads", "brand_voice")


def backup_runtime(data_dir: Path, config_dir: Path, target_dir: Path) -> dict[str, Any]:
    if target_dir.exists() and any(target_dir.iterdir()):
        raise ValueError(f"Backup target is not empty: {target_dir}")
    target_dir.mkdir(parents=True, exist_ok=True)
    source_db = data_dir / "blog_os.db"
    if not source_db.exists():
        raise FileNotFoundError(source_db)

    with sqlite3.connect(source_db) as source, sqlite3.connect(target_dir / "blog_os.db") as target:
        source.backup(target)

    for name in BACKUP_DIRS:
        source = data_dir / name
        if source.exists():
            shutil.copytree(source, target_dir / "data" / name)
    if config_dir.exists():
        shutil.copytree(config_dir, target_dir / "config")

    manifest = {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": ["blog_os.db", "data", "config"],
    }
    (target_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


def restore_runtime(
    backup_dir: Path,
    data_dir: Path,
    config_dir: Path,
    *,
    force: bool = False,
) -> None:
    if not (backup_dir / "manifest.json").exists() or not (backup_dir / "blog_os.db").exists():
        raise ValueError("Backup is incomplete")
    for destination in (data_dir, config_dir):
        if destination.exists() and any(destination.iterdir()) and not force:
            raise ValueError(f"Restore target is not empty: {destination}")
        if destination.exists() and force:
            shutil.rmtree(destination)
    data_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup_dir / "blog_os.db", data_dir / "blog_os.db")
    backup_data = backup_dir / "data"
    if backup_data.exists():
        for source in backup_data.iterdir():
            shutil.copytree(source, data_dir / source.name)
    backup_config = backup_dir / "config"
    if backup_config.exists():
        shutil.copytree(backup_config, config_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup or restore AI Content OS runtime data")
    parser.add_argument("action", choices=("backup", "restore"))
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--config-dir", type=Path, default=Path("config"))
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.action == "backup":
        backup_runtime(args.data_dir, args.config_dir, args.backup_dir)
    else:
        restore_runtime(args.backup_dir, args.data_dir, args.config_dir, force=args.force)


if __name__ == "__main__":
    main()
