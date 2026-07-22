from __future__ import annotations

from collections.abc import Generator
from typing import cast

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


def get_request_id(request: Request) -> str:
    return cast(str, request.state.request_id)


def get_app_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_database_session(request: Request) -> Generator[Session, None, None]:
    factory = cast(sessionmaker[Session], request.app.state.session_factory)
    session = factory()
    try:
        yield session
    finally:
        session.close()
