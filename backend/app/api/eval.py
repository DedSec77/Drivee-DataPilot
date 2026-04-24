from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from app.core.auth import require_api_token
from app.core.config import settings

router = APIRouter(dependencies=[Depends(require_api_token)])


def _results_dir() -> Path:
    env_dir = getattr(settings, "eval_results_dir", None)
    if env_dir:
        return Path(env_dir)
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "eval" / "results"
        if candidate.exists():
            return candidate
    return Path("eval/results")


@router.get("/eval/summary")
def eval_summary() -> dict[str, Any]:
    results_dir = _results_dir()
    report_json = results_dir / "report.json"
    if not report_json.exists():
        return {
            "status": "no_results",
            "hint_ru": (
                "Ещё не запускали eval. Запустите "
                "`docker compose exec backend python -m eval.run_eval`, "
                "затем обновите страницу."
            ),
            "looked_at": str(report_json),
        }
    try:
        data = json.loads(report_json.read_text(encoding="utf-8"))
    except Exception as e:
        return {"status": "parse_error", "hint_ru": str(e), "looked_at": str(report_json)}
    return {
        "status": "ok",
        "report": data,
        "mtime": report_json.stat().st_mtime,
    }


@router.get("/query-log")
def query_log(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    from sqlalchemy import select

    from app.db.models import QueryLog
    from app.db.session import SessionLocal

    limit = max(1, min(500, limit))
    offset = max(0, offset)
    with SessionLocal() as s:
        rows = (
            s.execute(select(QueryLog).order_by(QueryLog.log_id.desc()).offset(offset).limit(limit))
            .scalars()
            .all()
        )
        return [
            {
                "log_id": r.log_id,
                "ts": r.ts.isoformat() if r.ts else None,
                "nl_question": r.nl_question,
                "sql_generated": r.sql_generated,
                "sql_executed": r.sql_executed,
                "confidence": float(r.confidence) if r.confidence is not None else None,
                "guard_verdict": r.guard_verdict,
                "exec_ms": r.exec_ms,
                "result_rows": r.result_rows,
                "error": r.error,
            }
            for r in rows
        ]
