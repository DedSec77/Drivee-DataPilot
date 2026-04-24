from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import require_api_token
from app.core.retrieval import get_retriever
from app.core.scheduler import unregister_schedule
from app.db.models import SavedReport, Schedule
from app.db.session import get_session

router = APIRouter(dependencies=[Depends(require_api_token)])

SessionDep = Annotated[Session, Depends(get_session)]


class TemplateCreate(BaseModel):
    owner: str
    title: str = Field(..., min_length=1, max_length=200)
    nl_question: str
    sql_text: str
    chart_type: str | None = None


class TemplateDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    report_id: int
    owner: str
    title: str
    nl_question: str
    sql_text: str
    chart_type: str | None = None
    is_approved: bool
    is_template: bool


@router.get("/templates", response_model=list[TemplateDTO])
def list_templates(s: SessionDep, only_approved: bool = False) -> list[TemplateDTO]:
    q = select(SavedReport).where(SavedReport.is_template.is_(True))
    if only_approved:
        q = q.where(SavedReport.is_approved.is_(True))
    rows = s.execute(q).scalars().all()
    return [TemplateDTO.model_validate(r) for r in rows]


@router.post("/templates", response_model=TemplateDTO)
def save_template(req: TemplateCreate, s: SessionDep) -> TemplateDTO:
    row = SavedReport(
        owner=req.owner,
        title=req.title,
        nl_question=req.nl_question,
        sql_text=req.sql_text,
        chart_type=req.chart_type,
        is_approved=False,
        is_template=True,
    )
    s.add(row)
    s.commit()
    s.refresh(row)
    return TemplateDTO.model_validate(row)


@router.post("/templates/{report_id}/approve", response_model=TemplateDTO)
def approve_template(report_id: int, s: SessionDep) -> TemplateDTO:
    row = s.get(SavedReport, report_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    row.is_approved = True
    s.commit()
    s.refresh(row)

    try:
        get_retriever().add_approved_fewshot(
            report_id=row.report_id,
            nl_ru=row.nl_question,
            sql=row.sql_text,
            tags="approved,template",
        )
        logger.info(f"[templates] approved report_id={row.report_id} -> added as few-shot")
    except Exception as e:
        logger.warning(f"[templates] approve succeeded but few-shot indexing failed: {e}")

    return TemplateDTO.model_validate(row)


@router.delete("/templates/{report_id}")
def delete_template(report_id: int, s: SessionDep) -> dict[str, str | int]:
    row = s.get(SavedReport, report_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    was_approved = row.is_approved

    orphan_schedule_ids = (
        s.execute(select(Schedule.schedule_id).where(Schedule.report_id == report_id)).scalars().all()
    )

    s.delete(row)
    s.commit()

    for sid in orphan_schedule_ids:
        try:
            unregister_schedule(sid)
        except Exception as e:
            logger.warning(f"[templates] schedule unregister skipped id={sid}: {e}")

    if was_approved:
        try:
            get_retriever().few_col.delete(ids=[f"tpl-{report_id}"])
            logger.info(
                f"[templates] deleted report_id={report_id} "
                f"(incl. few-shot, unregistered {len(orphan_schedule_ids)} schedules)"
            )
        except Exception as e:
            logger.warning(f"[templates] deleted but few-shot unindex failed: {e}")
    else:
        logger.info(
            f"[templates] deleted report_id={report_id} (unregistered {len(orphan_schedule_ids)} schedules)"
        )

    return {"status": "deleted", "report_id": report_id}
