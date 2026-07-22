#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from app.core.config import Settings
from app.db.migrations import upgrade_database
from app.db.session import create_database_engine, create_session_factory
from app.services.bootstrap import bootstrap_existing_corpus, result_as_json


def parse_args() -> argparse.Namespace:
    backend_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Bootstrap the validated Atlas60 corpus.")
    parser.add_argument("--repository-root", type=Path, default=backend_root.parent)
    parser.add_argument("--storage-root", type=Path, default=backend_root / "storage")
    parser.add_argument("--database", type=Path, default=backend_root / "storage" / "atlas.db")
    parser.add_argument("--batch-size", type=int, default=32)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.storage_root.mkdir(parents=True, exist_ok=True)
    args.database.parent.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{args.database.resolve()}",
        storage_root=args.storage_root.resolve(),
    )
    upgrade_database(settings.database_url)
    engine = create_database_engine(settings.database_url)
    try:
        result = bootstrap_existing_corpus(
            repository_root=args.repository_root.resolve(),
            settings=settings,
            session_factory=create_session_factory(engine),
            batch_size=args.batch_size,
        )
        print(result_as_json(result))
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
