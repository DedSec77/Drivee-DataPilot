from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app.core.auth import require_admin_token
from app.core.rate_limit import rl_admin_read, rl_admin_write
from app.db.session import engine

router = APIRouter(dependencies=[Depends(require_admin_token)])

_TABLE_MAP = {
    "logs": "query_log",
    "templates": "saved_reports",
    "schedules": "schedules",
    "trips": "fct_trips",
}


class ResetRequest(BaseModel):
    logs: bool = False
    templates: bool = False
    schedules: bool = False
    trips: bool = False


@router.get("/admin/stats", dependencies=[rl_admin_read])
def admin_stats() -> dict[str, int]:
    out: dict[str, int] = {}
    with engine.connect() as conn:
        for key, table in _TABLE_MAP.items():
            try:
                row = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()
                out[key] = int(row or 0)
            except Exception:
                out[key] = 0
    return out


@router.post("/admin/reset", dependencies=[rl_admin_write])
def admin_reset(body: ResetRequest) -> dict[str, Any]:
    selected = [k for k, v in body.model_dump().items() if v]
    if not selected:
        raise HTTPException(
            status_code=400,
            detail="Не выбрано ни одной таблицы для очистки.",
        )

    deleted: dict[str, int] = {}
    with engine.begin() as conn:
        for key in selected:
            table = _TABLE_MAP[key]
            try:
                row = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()
                deleted[key] = int(row or 0)
            except Exception:
                deleted[key] = 0

        tables = [_TABLE_MAP[k] for k in selected]
        sql = "TRUNCATE TABLE " + ", ".join(tables) + " RESTART IDENTITY CASCADE"
        conn.execute(text(sql))

    return {
        "status": "ok",
        "deleted": deleted,
        "tables": [_TABLE_MAP[k] for k in selected],
    }
