from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field, field_validator

from app.core.auth import require_api_token, validate_role
from app.core.pipeline import run_ask
from app.core.rate_limit import rl_ask, rl_stream

router = APIRouter(dependencies=[Depends(require_api_token)])

_STREAM_DONE: tuple[str] = ("__done__",)


class ChatTurnDTO(BaseModel):
    question: str = Field(..., max_length=2000)
    kind: Literal["answer", "clarify", "error"] | None = None
    summary: str | None = Field(default=None, max_length=2000)
    sql: str | None = Field(default=None, max_length=8000)


class AskRequest(BaseModel):
    question: str = Field(..., max_length=2000)
    role: str = "business_user"
    allowed_city_ids: list[int] | None = Field(default=None)
    n_candidates: int | None = None
    chat_history: list[ChatTurnDTO] | None = Field(default=None)

    @field_validator("question")
    @classmethod
    def _strip_and_check(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question must not be empty after stripping whitespace")
        return v

    @field_validator("allowed_city_ids")
    @classmethod
    def _check_city_ids(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return None
        if any(c < 1 for c in v):
            raise ValueError("allowed_city_ids must be positive integers (>=1)")
        return v

    @field_validator("chat_history")
    @classmethod
    def _trim_history(cls, v: list[ChatTurnDTO] | None) -> list[ChatTurnDTO] | None:
        if not v:
            return None

        return v[-8:]


class AskResponseDTO(BaseModel):
    kind: str
    sql: str | None = None
    columns: list[str] | None = None
    rows: list[list[Any]] | None = None
    clarify_question: str | None = None
    clarify_options: list[dict[str, str]] | None = None
    explainer: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    chart_hint: str | None = None


def _build_user_ctx(req: AskRequest) -> dict[str, Any]:
    user_ctx: dict[str, Any] = {}
    if req.allowed_city_ids:
        user_ctx["allowed_city_ids"] = req.allowed_city_ids
    return user_ctx


def _build_history(req: AskRequest) -> list[dict[str, Any]] | None:
    if not req.chat_history:
        return None
    return [t.model_dump(exclude_none=True) for t in req.chat_history]


@router.post("/ask", response_model=AskResponseDTO, dependencies=[rl_ask])
def ask(req: AskRequest) -> AskResponseDTO:
    role = validate_role(req.role)
    result = run_ask(
        nl_question=req.question,
        user_ctx=_build_user_ctx(req),
        role=role,
        n_candidates=req.n_candidates,
        chat_history=_build_history(req),
    )
    return AskResponseDTO(**result.__dict__)


def _ndjson_line(event: dict[str, Any]) -> bytes:
    return (json.dumps(event, ensure_ascii=False, default=str) + "\n").encode("utf-8")


@router.post("/ask/stream", dependencies=[rl_stream])
async def ask_stream(req: AskRequest) -> StreamingResponse:
    role = validate_role(req.role)
    user_ctx = _build_user_ctx(req)
    history = _build_history(req)

    loop = asyncio.get_running_loop()
    started = time.time()
    queue: asyncio.Queue[Any] = asyncio.Queue()

    def on_progress(stage: str, label: str, detail: str | None) -> None:
        event = {
            "type": "stage",
            "stage": stage,
            "label": label,
            "detail": detail,
            "ms": int((time.time() - started) * 1000),
        }
        loop.call_soon_threadsafe(queue.put_nowait, event)

    async def driver() -> None:
        try:
            result = await asyncio.to_thread(
                run_ask,
                nl_question=req.question,
                user_ctx=user_ctx,
                role=role,
                n_candidates=req.n_candidates,
                chat_history=history,
                progress=on_progress,
            )
            await queue.put(
                {
                    "type": "result",
                    "result": AskResponseDTO(**result.__dict__).model_dump(),
                    "ms": int((time.time() - started) * 1000),
                }
            )
        except Exception as e:
            logger.exception(f"[ask-stream] pipeline crashed: {e}")
            await queue.put(
                {
                    "type": "error",
                    "error": {"code": "STREAM_ERROR", "hint_ru": str(e)},
                    "ms": int((time.time() - started) * 1000),
                }
            )
        finally:
            await queue.put(_STREAM_DONE)

    async def event_stream() -> AsyncIterator[bytes]:
        task = asyncio.create_task(driver())
        try:
            while True:
                event = await queue.get()
                if event is _STREAM_DONE:
                    return
                yield _ndjson_line(event)
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
    )
