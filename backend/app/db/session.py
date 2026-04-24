from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.datasource import (
    get_engine,
    get_session_factory,
    to_psycopg_dsn,
)


def __getattr__(name: str) -> Any:
    if name == "engine":
        return get_engine()
    if name == "SessionLocal":
        return get_session_factory()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_session() -> Iterator[Session]:
    with get_session_factory()() as s:
        yield s


@contextmanager
def raw_psycopg():
    with psycopg.connect(to_psycopg_dsn(settings.database_url), autocommit=False) as conn:
        yield conn
