#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.config import Settings
from app.db.migrations import upgrade_database
from app.db.session import create_database_engine, create_session_factory
from app.services.snapshots import verify_active_snapshot


def parse_args() -> argparse.Namespace:
    backend_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Verify Atlas database/index alignment.")
    parser.add_argument("--storage-root", type=Path, default=backend_root / "storage")
    parser.add_argument("--database", type=Path, default=backend_root / "storage" / "atlas.db")
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
    report = None
    try:
        factory = create_session_factory(engine)
        with factory() as session:
            report = verify_active_snapshot(session, settings)
        print(
            json.dumps(
                {
                    "ready": report.ready,
                    "errors": report.errors,
                    "indexVersion": report.index_version,
                    "vectorCount": report.vector_count,
                    "dimension": report.dimension,
                },
                indent=2,
            )
        )
    finally:
        engine.dispose()
    return 0 if report and report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
