from __future__ import annotations

import json
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import httpx
from loguru import logger
from openai import APIConnectionError, BadRequestError, OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from app.core.config import settings

CandidateProgress = Callable[[int, int, "str | None"], None]

_JSON_BLOCK = re.compile(r"\{[\s\S]*\}")
_SQL_BLOCK = re.compile(r"```sql\s*([\s\S]*?)```", re.IGNORECASE)


def _coerce_float(v: Any, default: float) -> float:
    if v is None or isinstance(v, bool):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


@dataclass
class LLMCandidate:
    sql: str | None
    clarify: str | None
    raw: str
    used_metrics: list[str]
    used_dimensions: list[str]
    time_range: str | None
    confidence: float
    explanation_ru: str
    clarify_options: list[dict[str, str]] | None = None


def _parse_clarify_options(data: dict[str, Any]) -> list[dict[str, str]] | None:
    raw_opts = data.get("options")
    if not isinstance(raw_opts, list):
        return None
    cleaned: list[dict[str, str]] = []
    for item in raw_opts:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        question = str(item.get("question", "")).strip()
        if label and question:
            cleaned.append({"label": label[:60], "question": question[:500]})
    return cleaned[:5] if cleaned else None


def _parse_model_output(raw: str) -> LLMCandidate:
    m = _JSON_BLOCK.search(raw)
    data: dict[str, Any] | None = None
    if m:
        try:
            parsed = json.loads(m.group(0))
            if isinstance(parsed, dict):
                data = parsed
        except json.JSONDecodeError:
            data = None

    if data is not None:
        if data.get("clarify"):
            return LLMCandidate(
                sql=None,
                clarify=str(data["clarify"]),
                raw=raw,
                used_metrics=[],
                used_dimensions=[],
                time_range=None,
                confidence=_coerce_float(data.get("confidence"), 0.3),
                explanation_ru=str(data.get("explanation_ru", "")),
                clarify_options=_parse_clarify_options(data),
            )
        used_metrics_raw = data.get("used_metrics") or []
        used_dimensions_raw = data.get("used_dimensions") or []
        return LLMCandidate(
            sql=(str(data.get("sql", "")).strip() or None),
            clarify=None,
            raw=raw,
            used_metrics=list(used_metrics_raw) if isinstance(used_metrics_raw, list) else [],
            used_dimensions=list(used_dimensions_raw) if isinstance(used_dimensions_raw, list) else [],
            time_range=data.get("time_range"),
            confidence=_coerce_float(data.get("confidence"), 0.6),
            explanation_ru=str(data.get("explanation_ru", "")),
        )

    fence = _SQL_BLOCK.search(raw)
    sql = fence.group(1).strip() if fence else raw.strip()
    return LLMCandidate(
        sql=sql,
        clarify=None,
        raw=raw,
        used_metrics=[],
        used_dimensions=[],
        time_range=None,
        confidence=0.5,
        explanation_ru="",
    )


class LlamaCppLLM:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        timeout_s: int,
        max_tokens: int,
        max_parallel: int = 1,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.max_parallel = max(1, max_parallel)
        self.client = OpenAI(
            api_key=api_key or "sk-no-key",
            base_url=self.base_url,
            http_client=httpx.Client(timeout=timeout_s),
        )
        self._supports_json_format: bool | None = None

    def is_up(self) -> bool:
        try:
            with httpx.Client(timeout=5.0) as c:
                r = c.get(f"{self.base_url.rstrip('/v1')}/health")
                return r.status_code == 200
        except Exception:
            return False

    @staticmethod
    def _extract_text(resp: Any) -> str:
        choices = getattr(resp, "choices", None) or []
        if not choices:
            raise RuntimeError("LLM returned no choices")
        msg = getattr(choices[0], "message", None)
        if msg is None:
            return ""
        return getattr(msg, "content", None) or ""

    @retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=1, max=6))
    def _chat(self, system: str, user: str, temperature: float) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }
        if self._supports_json_format is not False:
            try:
                resp = self.client.chat.completions.create(**kwargs, response_format={"type": "json_object"})
                self._supports_json_format = True
                return self._extract_text(resp)
            except BadRequestError:
                self._supports_json_format = False
            except APIConnectionError:
                raise
        resp = self.client.chat.completions.create(**kwargs)
        return self._extract_text(resp)

    def complete(self, system: str, user: str, temperature: float = 0.2) -> str:
        return self._chat(system, user, temperature)

    def generate(
        self,
        system: str,
        user: str,
        n: int = 3,
        *,
        on_candidate: CandidateProgress | None = None,
    ) -> list[LLMCandidate]:
        temperatures = [0.0, 0.3, 0.6][: max(1, n)]
        total = len(temperatures)
        outputs: list[LLMCandidate | None] = [None] * total
        done_count = 0

        def _one(idx: int, t: float) -> None:
            nonlocal done_count
            err: str | None = None
            try:
                raw = self.complete(system, user, temperature=t)
                outputs[idx] = _parse_model_output(raw)
            except Exception as e:
                err = str(e).splitlines()[0] if str(e) else type(e).__name__
                logger.warning(f"llama.cpp call failed at t={t}: {e}")
            finally:
                done_count += 1
                if on_candidate is not None:
                    try:
                        on_candidate(done_count, total, err)
                    except Exception as cb_err:
                        logger.warning(f"on_candidate callback raised: {cb_err}")

        workers = min(total, self.max_parallel)
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="llm-gen") as ex:
            list(ex.map(lambda args: _one(*args), enumerate(temperatures)))

        return [o for o in outputs if o is not None]

    def critic_fix(
        self,
        system: str,
        broken_sql: str,
        error: str,
        *,
        attempt: int = 1,
        prior_attempts: list[tuple[str, str]] | None = None,
        temperature: float | None = None,
    ) -> LLMCandidate | None:
        prior = prior_attempts or []
        history_block = ""
        if prior:
            lines = ["PRIOR FAILED ATTEMPTS (do NOT repeat any of these):"]
            for idx, (sql, err) in enumerate(prior, start=1):
                lines.append(f"  attempt {idx} SQL:\n```sql\n{sql}\n```\n  error: {err}")
            history_block = "\n".join(lines) + "\n\n"

        critic_user = (
            f"Critic retry {attempt}. Previous SQL failed validation. "
            "Return a corrected SQL in the same JSON format.\n\n"
            f"{history_block}"
            f"CURRENT FAILED SQL:\n```sql\n{broken_sql}\n```\n\n"
            f"CURRENT ERROR: {error}\n\n"
            "Fix only what is necessary. Keep the original intent. "
            "Pay special attention to time-window bounds - the right "
            "edge of an interval must NOT equal the left edge "
            "(e.g. for «на этой неделе» the right bound is `now()`, "
            "not `date_trunc('week', now())`)."
        )
        try:
            raw = self.complete(
                system, critic_user, temperature=temperature if temperature is not None else 0.0
            )
            return _parse_model_output(raw)
        except Exception as e:
            logger.warning(f"llama.cpp critic call failed: {e}")
            return None


class LLMRouter:
    def __init__(self) -> None:
        self.primary = LlamaCppLLM(
            base_url=settings.llama_cpp_url,
            model=settings.llama_cpp_model,
            api_key=settings.llama_cpp_api_key,
            timeout_s=settings.llama_cpp_timeout_s,
            max_tokens=settings.llama_cpp_max_tokens,
            max_parallel=settings.llama_cpp_max_parallel,
        )

    def generate(
        self,
        system: str,
        user: str,
        n: int = 3,
        *,
        on_candidate: CandidateProgress | None = None,
    ) -> list[LLMCandidate]:
        return self.primary.generate(system, user, n=n, on_candidate=on_candidate)

    def critic_fix(
        self,
        system: str,
        broken_sql: str,
        error: str,
        *,
        attempt: int = 1,
        prior_attempts: list[tuple[str, str]] | None = None,
        temperature: float | None = None,
    ) -> LLMCandidate | None:
        return self.primary.critic_fix(
            system,
            broken_sql,
            error,
            attempt=attempt,
            prior_attempts=prior_attempts,
            temperature=temperature,
        )


@lru_cache(maxsize=1)
def get_llm() -> LLMRouter:
    return LLMRouter()
