from __future__ import annotations

import re
from typing import Annotated, Any

from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import require_admin_token, require_api_token
from app.core.scheduler import (
    delete_scheduled_run,
    list_scheduled_runs,
    register_schedule,
    run_saved_report_now,
    unregister_schedule,
)
from app.db.models import SavedReport, Schedule
from app.db.session import get_session

router = APIRouter(dependencies=[Depends(require_api_token)])

SessionDep = Annotated[Session, Depends(get_session)]
AdminDep = Depends(require_admin_token)

_DEST_RE = re.compile(r"^[\w./:\-]+$")


class ScheduleCreate(BaseModel):
    report_id: int
    cron_expr: str = Field(..., min_length=1, max_length=200)
    destination: str = Field(..., min_length=1, max_length=200)

    @field_validator("cron_expr")
    @classmethod
    def _validate_cron(cls, v: str) -> str:
        v = v.strip()
        try:
            CronTrigger.from_crontab(v)
        except Exception as e:
            raise ValueError(f"Invalid cron expression: {e}") from e
        return v

    @field_validator("destination")
    @classmethod
    def _validate_destination(cls, v: str) -> str:
        v = v.strip()
        if ".." in v:
            raise ValueError("destination must not contain '..'")
        if not _DEST_RE.match(v):
            raise ValueError(
                "destination contains invalid characters (allowed: letters, digits, '_', '.', '/', ':', '-')"
            )
        return v


class ScheduleDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    schedule_id: int
    report_id: int | None
    cron_expr: str
    destination: str
    is_active: bool


class SchedulePatch(BaseModel):
    is_active: bool


@router.post(
    "/schedule",
    response_model=ScheduleDTO,
    dependencies=[AdminDep],
)
def create_schedule(req: ScheduleCreate, s: SessionDep) -> ScheduleDTO:
    report = s.get(SavedReport, req.report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    row = Schedule(
        report_id=req.report_id,
        cron_expr=req.cron_expr,
        destination=req.destination,
        is_active=True,
    )
    s.add(row)
    s.commit()
    s.refresh(row)

    try:
        register_schedule(row.schedule_id, row.report_id, row.cron_expr, row.destination)
    except Exception as e:
        logger.warning(f"[schedule] register failed for id={row.schedule_id}: {e}")
        s.delete(row)
        s.commit()
        raise HTTPException(
            status_code=422,
            detail=f"Failed to register schedule with APScheduler: {e}",
        ) from e

    return ScheduleDTO.model_validate(row)


@router.get("/schedule", response_model=list[ScheduleDTO])
def list_schedules(s: SessionDep) -> list[ScheduleDTO]:
    rows = s.execute(select(Schedule)).scalars().all()
    return [ScheduleDTO.model_validate(r) for r in rows]


@router.patch(
    "/schedule/{schedule_id}",
    response_model=ScheduleDTO,
    dependencies=[AdminDep],
)
def patch_schedule(
    schedule_id: int,
    req: SchedulePatch,
    s: SessionDep,
) -> ScheduleDTO:
    row = s.get(Schedule, schedule_id)
    if not row:
        raise HTTPException(status_code=404, detail="Schedule not found")

    if req.is_active == row.is_active:
        try:
            if req.is_active and row.report_id is not None:
                register_schedule(row.schedule_id, row.report_id, row.cron_expr, row.destination)
        except Exception as e:
            logger.warning(f"[schedule] idempotent re-register failed id={schedule_id}: {e}")
        return ScheduleDTO.model_validate(row)

    prev_active = row.is_active
    row.is_active = req.is_active
    try:
        s.flush()
        if req.is_active:
            if row.report_id is None:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot activate a schedule that has no report_id",
                )
            register_schedule(row.schedule_id, row.report_id, row.cron_expr, row.destination)
        else:
            unregister_schedule(row.schedule_id)
        s.commit()
    except HTTPException:
        s.rollback()
        raise
    except Exception as e:
        s.rollback()
        row.is_active = prev_active
        logger.exception(f"[schedule] patch failed id={schedule_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to toggle schedule: {e}") from e

    s.refresh(row)
    return ScheduleDTO.model_validate(row)


@router.delete(
    "/schedule/{schedule_id}",
    dependencies=[AdminDep],
)
def delete_schedule(schedule_id: int, s: SessionDep) -> dict[str, str | int]:
    row = s.get(Schedule, schedule_id)
    if not row:
        raise HTTPException(status_code=404, detail="Schedule not found")

    report_id = row.report_id
    cron_expr = row.cron_expr
    destination = row.destination

    unregister_schedule(schedule_id)

    try:
        s.delete(row)
        s.commit()
    except Exception as e:
        s.rollback()
        if report_id is not None and row.is_active:
            try:
                register_schedule(schedule_id, report_id, cron_expr, destination)
            except Exception as re_err:
                logger.error(
                    f"[schedule] delete rolled back, but re-register also failed id={schedule_id}: {re_err}"
                )
        logger.exception(f"[schedule] delete failed id={schedule_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete schedule: {e}") from e

    return {"status": "deleted", "schedule_id": schedule_id}


@router.post(
    "/schedule/{schedule_id}/run-now",
    dependencies=[AdminDep],
)
def run_now(schedule_id: int, s: SessionDep) -> dict[str, Any]:
    row = s.get(Schedule, schedule_id)
    if not row:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if row.report_id is None:
        raise HTTPException(status_code=400, detail="Schedule has no associated report_id")
    try:
        result = run_saved_report_now(row.report_id, row.destination, schedule_id=schedule_id)
    except Exception as e:
        logger.exception(f"[schedule] run-now failed for id={schedule_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to run report: {e}") from e
    return {"status": "ok", "schedule_id": schedule_id, **result}


@router.get("/schedule/runs")
def list_runs(report_id: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
    return list_scheduled_runs(report_id=report_id, limit=limit)


@router.delete(
    "/schedule/runs/{filename}",
    dependencies=[AdminDep],
)
def delete_run(filename: str) -> dict[str, str]:
    try:
        removed = delete_scheduled_run(filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not removed:
        raise HTTPException(status_code=404, detail="Run file not found")
    return {"status": "deleted", "filename": filename}
