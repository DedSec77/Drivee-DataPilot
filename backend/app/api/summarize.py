from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel, Field, field_validator

from app.core.auth import require_api_token
from app.core.llm import get_llm
from app.core.rate_limit import rl_summarize

router = APIRouter(dependencies=[Depends(require_api_token)])

_SYSTEM_PROMPT = (
    "Ты переводишь длинный бизнес-вопрос в короткую подпись для кнопки "
    "в интерфейсе.\n\n"
    "Жёсткие правила:\n"
    "- 2-4 слова, максимум 30 символов.\n"
    "- На русском.\n"
    "- Без кавычек, без точки в конце, без эмодзи, без префиксов.\n"
    "- Сохраняй главную метрику и/или разрез.\n\n"
    "Примеры:\n"
    "Вопрос: Топ-3 города по количеству отменённых заказов на этой неделе\n"
    "Подпись: Топ-3 по отменам\n\n"
    "Вопрос: Сколько отмен по городам за прошлую неделю?\n"
    "Подпись: Отмены по городам\n\n"
    "Вопрос: Сравни конверсию по каналам за последние 30 дней\n"
    "Подпись: Конверсия по каналам\n\n"
    "Вопрос: Средний чек по сегментам пользователей за прошлый месяц\n"
    "Подпись: Средний чек\n\n"
    "Вопрос: Сколько активных пользователей (MAU) за последние 30 дней?\n"
    "Подпись: MAU за месяц\n\n"
    "Верни ТОЛЬКО подпись, без слова «Подпись:», без пояснений."
)


class SummarizeRequest(BaseModel):
    prompt: str = Field(..., max_length=2000)

    @field_validator("prompt")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("prompt must not be empty after stripping whitespace")
        return v


class SummarizeResponse(BaseModel):
    label: str


_QUOTE_CHARS = "\"'«»“”„`"
_LABEL_PREFIX_RE = re.compile(r"^(?:подпись|label)\s*[:\-]\s*", re.IGNORECASE)


def _clean_label(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            for key in ("label", "title", "short", "answer", "result"):
                v = data.get(key)
                if isinstance(v, str) and v.strip():
                    text = v.strip()
                    break
    except (ValueError, TypeError):
        pass

    for line in text.splitlines():
        if line.strip():
            text = line.strip()
            break

    text = _LABEL_PREFIX_RE.sub("", text).strip()

    text = text.strip(_QUOTE_CHARS).strip()

    text = text.rstrip(".,;:!?").strip()

    if len(text) > 50:
        text = text[:47].rstrip() + "…"

    return text


@router.post("/summarize-prompt", response_model=SummarizeResponse, dependencies=[rl_summarize])
def summarize_prompt(req: SummarizeRequest) -> SummarizeResponse:
    llm = get_llm()
    try:
        raw = llm.primary.complete(_SYSTEM_PROMPT, req.prompt, temperature=0.0)
    except Exception as e:
        logger.warning(f"[summarize] LLM call failed: {e}")
        raise HTTPException(status_code=503, detail=f"LLM недоступен: {e}") from e

    label = _clean_label(raw)
    if not label:
        raise HTTPException(
            status_code=422,
            detail="Не удалось получить корректную подпись из ответа модели",
        )
    return SummarizeResponse(label=label)
