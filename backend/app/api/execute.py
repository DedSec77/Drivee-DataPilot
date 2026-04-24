from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.core.auth import require_api_token, validate_role
from app.core.datasource import get_current_dialect, get_engine
from app.core.guardrails import GuardError, build_guard_config, guard_sql
from app.core.rate_limit import rl_execute
from app.core.semantic import get_semantic
from app.core.serialization import serialize_value
from app.core.sql_transpile import transpile_sql
from app.db.session import raw_psycopg

router = APIRouter(dependencies=[Depends(require_api_token)])


class ExecuteRequest(BaseModel):
    sql: str = Field(..., min_length=1, max_length=20000)
    role: str = "business_user"
    allowed_city_ids: list[int] | None = None


class ExecuteResponse(BaseModel):
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    est_cost: float | None = None
    est_rows: int | None = None
    applied_rules: list[str]
    dialect: str


@router.post("/execute", response_model=ExecuteResponse, dependencies=[rl_execute])
def execute(req: ExecuteRequest) -> ExecuteResponse:
    role = validate_role(req.role)
    semantic = get_semantic()
    cfg = build_guard_config(semantic, role=role)
    ctx: dict[str, Any] = {}
    if req.allowed_city_ids:
        ctx["allowed_city_ids"] = req.allowed_city_ids

    dialect = get_current_dialect()

    if dialect == "postgres":
        with raw_psycopg() as conn:
            try:
                guard = guard_sql(req.sql, cfg, user_ctx=ctx, conn=conn)
            except GuardError as e:
                raise HTTPException(status_code=400, detail=e.to_dict()) from e
            with conn.cursor() as cur:
                cur.execute(guard.safe_sql)
                cols = [c.name for c in cur.description] if cur.description else []
                rows = cur.fetchall() if cur.description else []
        return ExecuteResponse(
            sql=guard.safe_sql,
            columns=cols,
            rows=[[serialize_value(v) for v in r] for r in rows],
            est_cost=guard.est_cost,
            est_rows=guard.est_rows,
            applied_rules=guard.applied_rules,
            dialect=dialect,
        )

    try:
        guard = guard_sql(req.sql, cfg, user_ctx=ctx, conn=None)
    except GuardError as e:
        raise HTTPException(status_code=400, detail=e.to_dict()) from e

    target_sql = transpile_sql(guard.safe_sql, dialect)
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text(target_sql))
        cols = list(result.keys())
        rows = [list(r) for r in result.fetchall()]

    return ExecuteResponse(
        sql=target_sql,
        columns=cols,
        rows=[[serialize_value(v) for v in r] for r in rows],
        est_cost=None,
        est_rows=None,
        applied_rules=guard.applied_rules,
        dialect=dialect,
    )
