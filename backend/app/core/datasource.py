from __future__ import annotations

import re
from threading import RLock
from typing import Any

from loguru import logger
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

SUPPORTED_DIALECTS: dict[str, str] = {
    "postgresql": "postgres",
    "mysql": "mysql",
}


def detect_dialect(dsn: str) -> str:
    scheme = dsn.split("://", 1)[0].lower()
    base = scheme.split("+", 1)[0]
    if base not in SUPPORTED_DIALECTS:
        raise ValueError(
            f"Unsupported DSN scheme '{scheme}'. Supported: {', '.join(sorted(SUPPORTED_DIALECTS.keys()))}"
        )
    return SUPPORTED_DIALECTS[base]


def normalise_dsn(dsn: str) -> str:
    scheme, _, rest = dsn.partition("://")
    if "+" in scheme:
        return dsn
    scheme = scheme.lower()
    if scheme == "postgresql":
        return f"postgresql+psycopg://{rest}"
    if scheme == "mysql":
        return f"mysql+pymysql://{rest}"
    return dsn


def _require_dsn(dsn: str) -> str:
    if not dsn or not dsn.strip():
        raise RuntimeError(
            "DATABASE_URL is empty. Set it via the environment "
            "(see .env.example) - credentials must never live in code."
        )
    return dsn


_LOCK = RLock()
_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None

_current_dialect: str = "postgres"


def get_current_dialect() -> str:
    return _current_dialect


def _build_engine() -> tuple[Engine, sessionmaker[Session]]:
    eng = create_engine(_require_dsn(settings.database_url), pool_pre_ping=True, future=True)
    sm = sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True)
    return eng, sm


def get_engine() -> Engine:
    global _engine, _SessionLocal
    with _LOCK:
        if _engine is None:
            _engine, _SessionLocal = _build_engine()
        return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _engine, _SessionLocal
    with _LOCK:
        if _SessionLocal is None:
            _engine, _SessionLocal = _build_engine()
        return _SessionLocal


def get_database_url() -> str:
    return settings.database_url


_PASSWORD_RE = re.compile(r"(://[^:/@]+:)([^@]+)(@)")


def mask_dsn(dsn: str) -> str:
    return _PASSWORD_RE.sub(r"\1***\3", dsn)


def to_psycopg_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+psycopg://", "postgresql://")


_PG_PROBE_SQL = "SELECT current_database(), current_setting('server_version')"
_MYSQL_PROBE_SQL = "SELECT database(), version()"


def probe_connection(dsn: str, timeout_s: int = 5) -> dict[str, Any]:
    dialect = detect_dialect(dsn)
    info: dict[str, Any] = {
        "server_version": None,
        "current_database": None,
        "dialect": dialect,
    }
    eng = create_engine(
        normalise_dsn(dsn),
        pool_pre_ping=True,
        future=True,
        connect_args={"connect_timeout": timeout_s} if dialect != "postgres" else {},
    )
    try:
        with eng.connect() as conn:
            probe = _PG_PROBE_SQL if dialect == "postgres" else _MYSQL_PROBE_SQL
            row = conn.execute(text(probe)).fetchone()
            if row:
                info["current_database"] = row[0]
                info["server_version"] = row[1]
    finally:
        eng.dispose()
    return info


def set_database_url(dsn: str) -> dict[str, Any]:
    global _engine, _SessionLocal, _current_dialect
    dsn = dsn.strip()
    if not dsn:
        raise ValueError("DSN must be a non-empty string")

    dsn = normalise_dsn(dsn)
    dialect = detect_dialect(dsn)
    info = probe_connection(dsn)

    new_engine = create_engine(dsn, pool_pre_ping=True, future=True)

    with new_engine.connect() as conn:
        conn.execute(text("SELECT 1"))

    with _LOCK:
        old_engine = _engine
        _engine = new_engine
        _SessionLocal = sessionmaker(bind=new_engine, autoflush=False, autocommit=False, future=True)
        _current_dialect = dialect
        settings.database_url = dsn

    if old_engine is not None:
        try:
            old_engine.dispose()
        except Exception as e:
            logger.warning(f"[datasource] old engine dispose failed: {e}")

    logger.info(f"[datasource] switched to {mask_dsn(dsn)} (dialect={dialect})")
    return info
