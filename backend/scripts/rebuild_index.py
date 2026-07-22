#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.config import Settings
from app.db.migrations import upgrade_database
from app.db.session import create_database_engine, create_session_factory
from app.services.embedding import SentenceTransformerEncoder
from app.services.index_coordinator import rebuild_active_index


def parse_args() -> argparse.Namespace:
    backend_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Re-embed SQLite chunks and atomically rebuild the Atlas FAISS index."
    )
    parser.add_argument("--storage-root", type=Path, default=backend_root / "storage")
    parser.add_argument("--database", type=Path, default=backend_root / "storage" / "atlas.db")
    parser.add_argument("--batch-size", type=int, default=32)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be at least 1")
    args.storage_root.mkdir(parents=True, exist_ok=True)
    args.database.parent.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{args.database.resolve()}",
        storage_root=args.storage_root.resolve(),
        embedding_batch_size=args.batch_size,
    )
    upgrade_database(settings.database_url)
    engine = create_database_engine(settings.database_url)
    try:
        factory = create_session_factory(engine)
        result = rebuild_active_index(
            settings=settings,
            session_factory=factory,
            encoder=SentenceTransformerEncoder(settings),
            batch_size=args.batch_size,
        )
        print(
            json.dumps(
                {
                    "status": "rebuilt",
                    "indexVersion": result.index_version,
                    "previousIndexVersion": result.previous_index_version,
                    "vectorCount": result.vector_count,
                    "dimension": settings.embedding_dimension,
                },
                indent=2,
            )
        )
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
