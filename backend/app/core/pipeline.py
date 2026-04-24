from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import sqlglot
from loguru import logger
from sqlglot import expressions as exp

from app.core.config import settings
from app.core.garbage import looks_like_garbage
from app.core.guardrails import GuardError, GuardResult, build_guard_config, guard_sql
from app.core.interpretation import build_interpretation
from app.core.llm import LLMCandidate, get_llm
from app.core.retrieval import Retrieved, get_retriever
from app.core.selector import (
    ScoredCandidate,
    pick_best,
    score_candidates,
    to_explainer,
)
from app.core.semantic import SemanticModel, get_semantic
from app.core.serialization import serialize_value
from app.core.value_linker import ValueLink, get_value_linker
from app.core.voting import (
    VotingResult,
    execute_and_vote,
    voting_summary_for_log,
)
from app.db.session import SessionLocal, raw_psycopg
from prompts.system_ru import SYSTEM_PROMPT, build_schema_snippet, build_user_message

_IDENT_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")

ProgressCallback = Callable[[str, str, "str | None"], None]


def _emit(
    progress: ProgressCallback | None,
    stage: str,
    label: str,
    detail: str | None = None,
) -> None:
    if progress is None:
        return
    try:
        progress(stage, label, detail)
    except Exception as e:
        logger.warning(f"[progress] callback raised, ignoring: {e}")


_HALLUCINATION_HINTS: dict[str, str] = {
    "eta_minutes": "duration_minutes",
    "promised_eta": "duration_minutes",
    "actual_eta": "duration_minutes",
    "lateness": "duration_minutes",
    "delay_minutes": "duration_minutes",
    "completion_time": "duration_minutes",
    "session_duration": "duration_minutes",
}


def _detect_hallucination(sql: str | None, semantic: SemanticModel) -> str | None:
    if not sql:
        return None
    try:
        tree = sqlglot.parse_one(sql, read="postgres")
    except Exception:
        return None

    allowed_columns: set[str] = set()
    for fact in semantic.facts.values():
        allowed_columns.update(_extract_column_names(fact.time_column))
        for m in fact.measures:
            allowed_columns.update(_extract_column_names(m.expr))
        for d in fact.dimensions:
            allowed_columns.update(_extract_column_names(d.expr))
            if d.join:
                allowed_columns.update(_extract_column_names(d.join))
    for metric in semantic.metrics.values():
        allowed_columns.update(_extract_column_names(metric.expr))

    actual_columns: set[str] = {c.name.lower() for c in tree.find_all(exp.Column)}

    for token in actual_columns:
        for hint, suggested in _HALLUCINATION_HINTS.items():
            if hint in token and token not in allowed_columns:
                logger.warning(
                    f"[hallucination-guard] suspicious column '{token}' "
                    f"(hint matches '{hint}', suggest '{suggested}') in SQL"
                )
                return token
    return None


@dataclass
class AskResponse:
    kind: str
    sql: str | None = None
    columns: list[str] | None = None
    rows: list[list[Any]] | None = None
    clarify_question: str | None = None
    clarify_options: list[dict[str, str]] | None = None
    explainer: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    chart_hint: str | None = None


_CLARIFY_FALLBACKS: list[tuple[tuple[str, ...], list[dict[str, str]]]] = [
    (
        ("продаж", "выручк", "доход", "продажи"),
        [
            {"label": "Выручка", "question": "Сколько выручки за последние 7 дней по городам?"},
            {"label": "Число поездок", "question": "Сколько поездок за последние 7 дней по городам?"},
            {"label": "Средний чек", "question": "Средний чек поездки за последние 7 дней по городам"},
            {
                "label": "Активные пользователи",
                "question": "Сколько активных пользователей (MAU) за последние 30 дней?",
            },
        ],
    ),
    (
        ("отмен", "cancel"),
        [
            {"label": "Всего отмен", "question": "Сколько всего отмен за прошлую неделю по городам?"},
            {"label": "Доля отмен", "question": "Какая доля отмен за прошлую неделю по городам?"},
            {
                "label": "По вине водителя",
                "question": "Сколько отмен по вине водителя за прошлую неделю по городам?",
            },
            {
                "label": "По вине пассажира",
                "question": "Сколько отмен по вине пассажира за прошлую неделю по городам?",
            },
        ],
    ),
    (
        ("конверс", "completion", "успешн"),
        [
            {
                "label": "Доля завершённых",
                "question": "Какая доля завершённых поездок за последние 7 дней по городам?",
            },
            {"label": "По каналам", "question": "Доля завершённых поездок по каналам за последние 30 дней"},
            {"label": "Неделя-к-неделе", "question": "Сравни долю завершённых поездок неделя-к-неделе"},
        ],
    ),
    (
        ("eta", "длительн", "опозд"),
        [
            {
                "label": "Средняя длительность",
                "question": "Средняя длительность поездки за последние 7 дней по городам",
            },
            {"label": "По часам", "question": "Средняя длительность поездки по часам за последние 7 дней"},
            {
                "label": "По каналам",
                "question": "Средняя длительность поездки по каналам за последние 7 дней",
            },
        ],
    ),
    (
        ("пользовател", "клиент", "пассажир", "user", "rider"),
        [
            {
                "label": "Активные (MAU)",
                "question": "Сколько уникальных пассажиров (MAU) за последние 30 дней?",
            },
            {
                "label": "Новые сегменты",
                "question": "Сколько поездок по сегментам пользователей за последние 30 дней?",
            },
            {
                "label": "По городам",
                "question": "Сколько уникальных пассажиров за последние 30 дней по городам?",
            },
        ],
    ),
]


def _fallback_clarify_options(nl_question: str) -> list[dict[str, str]] | None:
    q = nl_question.lower()
    for stems, opts in _CLARIFY_FALLBACKS:
        if any(s in q for s in stems):
            return opts
    return None


def _log_query_safe(
    nl_question: str,
    response: AskResponse,
    exec_ms: int | None = None,
    *,
    voting_summary: dict[str, Any] | None = None,
) -> None:
    try:
        from app.db.models import QueryLog

        confidence = None
        sql_generated = response.sql
        sql_executed = response.sql if response.kind == "answer" else None
        if response.explainer and "confidence" in response.explainer:
            confidence = float(response.explainer["confidence"])
        if response.kind == "error" and response.error:
            guard_verdict = response.error.get("code", "ERROR")
        elif response.kind == "clarify":
            guard_verdict = "CLARIFY"
        elif response.kind == "answer":
            guard_verdict = "OK"
        else:
            guard_verdict = response.kind.upper()

        err_msg = None
        if response.kind == "error" and response.error:
            err_msg = response.error.get("hint_ru") or str(response.error)

        with SessionLocal() as s:
            s.add(
                QueryLog(
                    nl_question=nl_question[:2000],
                    sql_generated=sql_generated,
                    sql_executed=sql_executed,
                    confidence=confidence,
                    guard_verdict=guard_verdict,
                    exec_ms=exec_ms,
                    result_rows=len(response.rows) if response.rows else None,
                    error=err_msg,
                    voting_summary=voting_summary,
                )
            )
            s.commit()
    except Exception as e:
        logger.warning(f"[query_log] insert failed (non-fatal): {e}")


def _build_retrieved_payload(r: Retrieved) -> dict[str, Any]:
    return {
        "entities": [{"name": e["name"], "phrase": e["phrase"]} for e in r.entities],
        "measures": [{"name": m["name"], "fact": m["fact"], "phrase": m["phrase"]} for m in r.measures],
        "dimensions": [{"name": d["name"], "fact": d["fact"], "phrase": d["phrase"]} for d in r.dimensions],
        "metrics": [{"name": m["name"], "phrase": m["phrase"]} for m in r.metrics],
    }


def _columns_shortlist(semantic: SemanticModel, r: Retrieved) -> set[str]:
    measures_by_name: dict[str, str] = {}
    dim_index: dict[str, tuple[str, str | None]] = {}
    for fact in semantic.facts.values():
        for m in fact.measures:
            measures_by_name[m.name] = m.expr
        for d in fact.dimensions:
            dim_index[d.name] = (d.expr, d.join)

    cols: set[str] = set()
    for m_hit in r.measures:
        expr = measures_by_name.get(m_hit["name"])
        if expr:
            cols.update(_extract_column_names(expr))
    for d_hit in r.dimensions:
        entry = dim_index.get(d_hit["name"])
        if entry:
            expr, join = entry
            cols.update(_extract_column_names(expr))
            if join:
                cols.update(_extract_column_names(join))
    for fact in semantic.facts.values():
        cols.add(fact.time_column)
    return {c for c in cols if c}


def _extract_column_names(text: str) -> set[str]:
    tokens = _IDENT_RE.findall(text)
    return {t.lower() for t in tokens if not t.isupper() and len(t) > 2}


def _guess_chart(
    sql: str,
    columns: list[str],
    rows: list[list[Any]],
    nl_question: str = "",
) -> str:
    if not rows:
        return "empty"
    cols_lc = [c.lower() for c in columns]
    if any("wk" in c or "week" in c or "date" in c for c in cols_lc):
        return "line"
    sql_lc = sql.lower()
    nl_lc = nl_question.lower()
    looks_share = (
        any(kw in sql_lc for kw in ("share", "доля", "ratio", "percent", "rate"))
        or any("rate" in c or "share" in c or "ratio" in c or "pct" in c for c in cols_lc)
        or any(kw in nl_lc for kw in ("доля", "процент", "share", "топ", "top "))
    )
    if len(columns) == 2 and len(rows) <= 10 and looks_share:
        return "pie"
    if len(columns) == 2 and "limit" in sql_lc and len(rows) <= 6:
        return "pie"
    if len(columns) == 2 and len(rows) <= 50:
        return "bar"
    if len(columns) >= 3:
        return "table"
    return "bar" if len(rows) <= 20 else "table"


def run_ask(
    nl_question: str,
    user_ctx: dict[str, Any] | None = None,
    *,
    role: str = "business_user",
    n_candidates: int | None = None,
    chat_history: list[dict[str, Any]] | None = None,
    progress: ProgressCallback | None = None,
) -> AskResponse:
    t_start = time.time()
    response: AskResponse | None = None
    sql_exec_ms: int | None = None
    voting_summary: dict[str, Any] | None = None
    try:
        response, sql_exec_ms, voting_summary = _run_ask_impl(
            nl_question,
            user_ctx,
            role=role,
            n_candidates=n_candidates,
            chat_history=chat_history,
            progress=progress,
        )
        return response
    except Exception as e:
        logger.exception(f"[ask] unhandled error: {e}")
        response = AskResponse(
            kind="error",
            error={"code": "UNHANDLED", "hint_ru": f"Внутренняя ошибка: {e}"},
        )
        return response
    finally:
        total_ms = int((time.time() - t_start) * 1000)
        if response is not None:
            _log_query_safe(
                nl_question,
                response,
                exec_ms=sql_exec_ms or total_ms,
                voting_summary=voting_summary,
            )


_GARBAGE_CLARIFY_OPTIONS: list[dict[str, str]] = [
    {"label": "Отмены по городам", "question": "Сколько отмен по городам за прошлую неделю?"},
    {"label": "Конверсия по каналам", "question": "Сравни конверсию по каналам за последние 30 дней"},
    {"label": "Средний чек", "question": "Средний чек по сегментам пользователей за прошлый месяц"},
]
_OFFTOPIC_DISTANCE_THRESHOLD = 0.92


def _garbage_clarify() -> AskResponse:
    return AskResponse(
        kind="clarify",
        clarify_question=(
            "Не удалось понять вопрос. Напишите, что именно вас интересует: "
            "например, «Сколько поездок было вчера по Москве?» или "
            "«Сравни конверсию по каналам за последние 30 дней»."
        ),
        clarify_options=list(_GARBAGE_CLARIFY_OPTIONS),
    )


def _offtopic_clarify(nl_question: str) -> AskResponse:
    return AskResponse(
        kind="clarify",
        clarify_question=(
            "Вопрос не похож на запрос о данных Drivee. Попробуйте "
            "сформулировать про поездки, отмены, водителей, выручку, "
            "каналы заказа или города."
        ),
        clarify_options=_fallback_clarify_options(nl_question) or list(_GARBAGE_CLARIFY_OPTIONS),
    )


def _is_offtopic(retrieved: Retrieved) -> bool:
    return (
        retrieved.best_sem_distance > _OFFTOPIC_DISTANCE_THRESHOLD
        and retrieved.best_few_distance > _OFFTOPIC_DISTANCE_THRESHOLD
    )


def _guard_candidates(
    candidates: list[LLMCandidate],
    guard_cfg,
    user_ctx: dict[str, Any],
    progress: ProgressCallback | None = None,
) -> list[tuple[GuardResult | None, str | None]]:
    results: list[tuple[GuardResult | None, str | None]] = []
    total = len(candidates)
    with raw_psycopg() as conn:
        for idx, cand in enumerate(candidates, start=1):
            _emit(
                progress,
                "guarding",
                "Проверяю безопасность кандидатов…",
                f"{idx}/{total}",
            )
            if not cand.sql:
                results.append((None, "no_sql"))
                continue
            try:
                res = guard_sql(cand.sql, guard_cfg, user_ctx=user_ctx, conn=conn)
                results.append((res, None))
            except GuardError as e:
                results.append((None, f"{e.code}: {e.user_hint_ru}"))
            except Exception as e:
                results.append((None, f"RUNTIME: {e}"))
    return results


_CRITIC_RETRY_TEMPS: tuple[float, ...] = (0.0, 0.2, 0.4)


def _try_critic_fix(
    best: ScoredCandidate,
    llm,
    guard_cfg,
    user_ctx: dict[str, Any],
    *,
    max_attempts: int = 3,
    progress: ProgressCallback | None = None,
) -> ScoredCandidate | None:
    broken = best.llm.sql or ""
    err = best.guard_error or "generation failed"
    history: list[tuple[str, str]] = []

    for attempt in range(1, max_attempts + 1):
        _emit(
            progress,
            "critic",
            "Прошу модель починить SQL…",
            f"попытка {attempt}/{max_attempts}: {err}",
        )
        logger.info(f"[critic] attempt {attempt}/{max_attempts}: {err}")
        temperature = _CRITIC_RETRY_TEMPS[min(attempt - 1, len(_CRITIC_RETRY_TEMPS) - 1)]
        fixed = llm.critic_fix(
            SYSTEM_PROMPT,
            broken,
            err,
            attempt=attempt,
            prior_attempts=list(history),
            temperature=temperature,
        )
        if not fixed or not fixed.sql:
            history.append((broken, f"{err} (LLM returned empty)"))
            continue
        with raw_psycopg() as conn:
            try:
                res = guard_sql(fixed.sql, guard_cfg, user_ctx=user_ctx, conn=conn)
            except GuardError as e:
                logger.warning(f"[critic] attempt {attempt} still failing: {e}")
                history.append((fixed.sql, f"{e.code}: {e.user_hint_ru}"))

                broken = fixed.sql
                err = f"{e.code}: {e.user_hint_ru}"
                continue
        return ScoredCandidate(
            llm=fixed,
            guard=res,
            guard_error=None,
            score=max(0.0, best.score * (0.95 - 0.1 * (attempt - 1)) + 0.05),
            components={
                **best.components,
                "critic_fixed": 1.0,
                "critic_attempts": float(attempt),
            },
        )
    return None


_EMPTY_OK_HINTS: frozenset[str] = frozenset(
    {
        "никогда",
        "не было",
        "не происходило",
        "ни разу",
        "за всё время",
        "за всю историю",
    }
)


def _verify_empty_result(
    best: ScoredCandidate,
    nl_question: str,
    semantic: SemanticModel,
    llm,
    guard_cfg,
    user_ctx: dict[str, Any],
    *,
    progress: ProgressCallback | None = None,
) -> ScoredCandidate | None:
    nl_lc = nl_question.lower()
    if any(hint in nl_lc for hint in _EMPTY_OK_HINTS):
        return None
    safe_sql = best.guard.safe_sql if best.guard else ""
    if not safe_sql:
        return None

    time_cols_lc = {f.time_column.lower() for f in semantic.facts.values() if f.time_column}
    if not time_cols_lc or not any(c in safe_sql.lower() for c in time_cols_lc):
        return None

    _emit(
        progress,
        "verifying",
        "Перепроверяю пустой результат…",
        "0 строк при наличии time-фильтра",
    )

    err = (
        "The previous SQL executed but returned ZERO rows. The most "
        "likely cause is an empty time interval (e.g. WHERE col >= X "
        "AND col < X with the same X on both sides). Re-check the "
        "WHERE bounds and return a corrected query."
    )
    fixed = llm.critic_fix(
        SYSTEM_PROMPT,
        safe_sql,
        err,
        attempt=1,
        prior_attempts=[(safe_sql, "returned 0 rows")],
        temperature=0.0,
    )
    if not fixed or not fixed.sql:
        return None
    with raw_psycopg() as conn:
        try:
            res = guard_sql(fixed.sql, guard_cfg, user_ctx=user_ctx, conn=conn)
        except GuardError as e:
            logger.warning(f"[verify-empty] critic SQL also failed guardrails: {e}")
            return None
    return ScoredCandidate(
        llm=fixed,
        guard=res,
        guard_error=None,
        score=best.score,
        components={**best.components, "verified_empty": 1.0},
    )


def _hallucination_clarify(
    suspicious: str,
    nl_question: str,
    best: ScoredCandidate,
) -> AskResponse:
    suggested = next(
        (v for k, v in _HALLUCINATION_HINTS.items() if k in suspicious),
        "duration_minutes",
    )
    return AskResponse(
        kind="clarify",
        clarify_question=(
            f"В схеме нет колонки `{suspicious}`. Скорее всего вы имели в виду "
            f"`{suggested}`. Использовать её?"
        ),
        clarify_options=[
            {
                "label": f"Использовать {suggested}",
                "question": (f"{nl_question} (используй колонку {suggested} вместо {suspicious})"),
            },
            {
                "label": "Средняя длительность",
                "question": "Средняя длительность поездки за последние 7 дней по городам",
            },
            {
                "label": "Список доступных метрик",
                "question": "Покажи список доступных метрик и колонок",
            },
        ],
        explainer=to_explainer(best),
        sql=best.guard.safe_sql if best.guard else None,
    )


def _execute_safe_sql(
    safe_sql: str,
    best: ScoredCandidate,
) -> tuple[AskResponse | None, list[str], list[Any], int]:
    t0 = time.time()
    with raw_psycopg() as conn, conn.cursor() as cur:
        try:
            cur.execute(safe_sql)
            cols = [c.name for c in cur.description] if cur.description else []
            rows = cur.fetchall() if cur.description else []
        except Exception as e:
            return (
                AskResponse(
                    kind="error",
                    sql=safe_sql,
                    error={"code": "DB_ERROR", "hint_ru": str(e)},
                    explainer=to_explainer(best),
                ),
                [],
                [],
                int((time.time() - t0) * 1000),
            )
    return None, cols, rows, int((time.time() - t0) * 1000)


def _run_ask_impl(
    nl_question: str,
    user_ctx: dict[str, Any] | None = None,
    *,
    role: str = "business_user",
    n_candidates: int | None = None,
    chat_history: list[dict[str, Any]] | None = None,
    progress: ProgressCallback | None = None,
) -> tuple[AskResponse, int | None, dict[str, Any] | None]:
    user_ctx = user_ctx or {}
    n = n_candidates or settings.candidates_n

    voting_payload: dict[str, Any] | None = None

    semantic = get_semantic()
    llm = get_llm()
    retriever = get_retriever()

    if looks_like_garbage(nl_question.strip()):
        return _garbage_clarify(), None, voting_payload

    _emit(progress, "retrieving", "Ищу подходящие сущности и метрики…", "эмбеддинг вопроса")
    t0 = time.time()
    retrieved = retriever.retrieve(nl_question, k_sem=10, k_few=3)
    logger.info(
        f"[retrieve] {time.time() - t0:.2f}s  "
        f"sem_d={retrieved.best_sem_distance:.2f} few_d={retrieved.best_few_distance:.2f}  "
        f"hits: ent={len(retrieved.entities)} meas={len(retrieved.measures)} "
        f"dim={len(retrieved.dimensions)} met={len(retrieved.metrics)} "
        f"fs={len(retrieved.fewshots)}"
    )
    _emit(
        progress,
        "retrieving",
        "Ищу подходящие сущности и метрики…",
        f"найдено: meas={len(retrieved.measures)} "
        f"dim={len(retrieved.dimensions)} met={len(retrieved.metrics)} "
        f"fewshot={len(retrieved.fewshots)}",
    )

    if _is_offtopic(retrieved):
        return _offtopic_clarify(nl_question), None, voting_payload

    value_links_payload: list[dict[str, Any]] = []
    if settings.value_linking_enabled:
        try:
            vl = get_value_linker()
            links: list[ValueLink] = vl.link(nl_question, max_links=settings.value_linking_max_links)
            value_links_payload = [
                {
                    "token": link.token,
                    "column": link.column,
                    "value": link.db_value,
                    "match": link.method,
                    "score": round(1.0 - link.distance, 2),
                }
                for link in links
            ]
            if value_links_payload:
                preview = ", ".join(f"{link['token']}→{link['value']}" for link in value_links_payload[:3])
                _emit(
                    progress,
                    "linking",
                    "Связываю значения из вопроса с данными…",
                    f"найдено {len(value_links_payload)}: {preview}",
                )
                logger.info(
                    f"[value-link] {len(value_links_payload)} match(es): "
                    f"{[(link['token'], link['value']) for link in value_links_payload]}"
                )
        except Exception as e:
            logger.warning(f"[value-link] failed (non-fatal): {e}")

    user_msg = build_user_message(
        nl_question=nl_question,
        retrieved=_build_retrieved_payload(retrieved),
        schema_snippet=build_schema_snippet(semantic),
        time_expressions_ru=semantic.time_expressions_ru,
        cities_canonical_ru=semantic.cities_canonical_ru,
        fewshots=retrieved.fewshots,
        chat_history=chat_history,
        value_links=value_links_payload or None,
    )

    _emit(progress, "generating", "Генерирую варианты SQL…", f"0/{n} готов")
    t0 = time.time()

    def _on_cand(done: int, total: int, err: str | None) -> None:
        suffix = f" ({err.splitlines()[0][:60]})" if err else ""
        _emit(
            progress,
            "generating",
            "Генерирую варианты SQL…",
            f"{done}/{total} готов{suffix}",
        )

    candidates: list[LLMCandidate] = llm.generate(SYSTEM_PROMPT, user_msg, n=n, on_candidate=_on_cand)
    logger.info(f"[generate] {time.time() - t0:.2f}s  candidates={len(candidates)}")

    clarify_cand = next((c for c in candidates if c.clarify), None)
    if clarify_cand and not any(c.sql for c in candidates):
        return (
            AskResponse(
                kind="clarify",
                clarify_question=clarify_cand.clarify,
                clarify_options=clarify_cand.clarify_options or _fallback_clarify_options(nl_question),
            ),
            None,
            voting_payload,
        )

    guard_cfg = build_guard_config(semantic, role=role)
    guard_results = _guard_candidates(candidates, guard_cfg, user_ctx, progress=progress)
    _emit(progress, "scoring", "Сравниваю кандидатов и выбираю лучший…")
    retrieved_columns = _columns_shortlist(semantic, retrieved)
    scored = score_candidates(candidates, guard_results, retrieved_columns)

    best, should_clarify = pick_best(scored, threshold=settings.confidence_threshold)

    critic_used = False
    if best and (best.guard is None or best.guard_error is not None):
        fixed_scored = _try_critic_fix(
            best,
            llm,
            guard_cfg,
            user_ctx,
            max_attempts=settings.critic_max_attempts,
            progress=progress,
        )
        if fixed_scored is not None:
            scored = [fixed_scored, *scored]
            best = fixed_scored
            should_clarify = best.score < settings.confidence_threshold
            critic_used = True

    voting: VotingResult | None = None

    best_idx: int | None = None
    if (
        not critic_used
        and settings.voting_enabled
        and any(c.guard is not None and not c.guard_error for c in scored)
    ):
        _emit(progress, "voting", "Голосую по результатам исполнения…")
        voting = execute_and_vote(
            scored,
            timeout_s=settings.voting_timeout_s,
            max_executions=settings.voting_max_executions,
            max_parallel=settings.voting_max_parallel,
        )
        voting_payload = voting_summary_for_log(voting)
        _emit(
            progress,
            "voting",
            "Голосую по результатам исполнения…",
            voting.rationale,
        )
        if voting.successful_count > 0:
            scored = score_candidates(
                candidates,
                guard_results,
                retrieved_columns,
                voting_result=voting,
            )
            best, should_clarify = pick_best(scored, threshold=settings.confidence_threshold)
            best_idx = next((i for i, c in enumerate(scored) if c is best), None)

            if (
                voting.successful_count > 1
                and voting.consensus_strength < settings.voting_abstain_consensus
                and best is not None
                and best.guard is not None
                and not should_clarify
                and best.score < settings.confidence_threshold + settings.voting_abstain_score_buffer
            ):
                logger.info(
                    f"[abstention] forced clarify: consensus={voting.consensus_strength:.2f} "
                    f"score={best.score:.2f} thr={settings.confidence_threshold}"
                )
                should_clarify = True

            elif voting.successful_count > 1 and voting.consensus_strength >= 1.0 and best is not None:
                from dataclasses import replace as _replace

                bonus = min(1.0, best.score * settings.voting_consensus_bonus)
                best = _replace(best, score=bonus)

    if best is None or best.guard is None:
        msg = best.guard_error if best else "no candidates"
        return (
            AskResponse(
                kind="error",
                error={"code": "NO_SAFE_SQL", "hint_ru": msg or "Не удалось сгенерировать безопасный SQL."},
            ),
            None,
            voting_payload,
        )

    if should_clarify:
        clarify = (
            best.llm.clarify or "Запрос неоднозначный. Уточните: какую метрику посчитать и за какой период?"
        )
        return (
            AskResponse(
                kind="clarify",
                clarify_question=clarify,
                clarify_options=best.llm.clarify_options or _fallback_clarify_options(nl_question),
                explainer=to_explainer(best),
                sql=best.guard.safe_sql,
            ),
            None,
            voting_payload,
        )

    suspicious = _detect_hallucination(best.guard.safe_sql, semantic)
    if suspicious:
        return _hallucination_clarify(suspicious, nl_question, best), None, voting_payload

    safe_sql = best.guard.safe_sql

    err_response = None
    cols: list[str]
    rows: list[Any]
    exec_ms: int
    reused_trace = False
    if voting is not None and best_idx is not None:
        trace = voting.trace_for(best_idx)
        if trace is not None and trace.error is None and trace.fingerprint:
            _emit(
                progress,
                "executing",
                "Запускаю SQL в Postgres…",
                f"результат из голосования: {trace.exec_ms} мс, {trace.row_count} строк",
            )
            cols = list(trace.columns)
            rows = list(trace.rows)
            exec_ms = trace.exec_ms
            reused_trace = True
            logger.info(
                f"[execute] reused voting trace: {exec_ms}ms rows={len(rows)} "
                f"fingerprint={trace.fingerprint[:8]}"
            )
    if not reused_trace:
        _emit(progress, "executing", "Запускаю SQL в Postgres…")
        err_response, cols, rows, exec_ms = _execute_safe_sql(safe_sql, best)
        if err_response is not None:
            return err_response, None, voting_payload
        logger.info(f"[execute] {exec_ms}ms rows={len(rows)}")

    if settings.verify_empty_results and not rows and best.guard is not None:
        verified = _verify_empty_result(
            best,
            nl_question,
            semantic,
            llm,
            guard_cfg,
            user_ctx,
            progress=progress,
        )
        if verified is not None and verified.guard is not None:
            new_sql = verified.guard.safe_sql
            new_err, new_cols, new_rows, new_ms = _execute_safe_sql(new_sql, verified)
            if new_err is None and new_rows:
                logger.info(f"[verify-empty] retry succeeded: {len(new_rows)} rows in {new_ms}ms")
                best = verified
                safe_sql = new_sql
                cols, rows = new_cols, new_rows
                exec_ms = (exec_ms or 0) + new_ms

    rows_json = [[serialize_value(v) for v in row] for row in rows]

    _emit(progress, "interpreting", "Собираю объяснение «как я понял»…")
    explainer_payload = to_explainer(best)
    interpretation = build_interpretation(
        nl_question=nl_question,
        sql=safe_sql,
        explainer=explainer_payload,
        semantic=semantic,
    )
    explainer_payload["interpretation"] = interpretation
    if not explainer_payload.get("explanation_ru"):
        explainer_payload["explanation_ru"] = interpretation["summary_ru"]

    _emit(progress, "done", "Готово", None)

    return (
        AskResponse(
            kind="answer",
            sql=safe_sql,
            columns=cols,
            rows=rows_json,
            explainer=explainer_payload,
            chart_hint=_guess_chart(safe_sql, cols, rows, nl_question=nl_question),
        ),
        exec_ms,
        voting_payload,
    )


def _serialize(v: Any) -> Any:
    return serialize_value(v)
