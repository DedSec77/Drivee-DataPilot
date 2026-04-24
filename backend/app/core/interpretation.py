from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import sqlglot
from sqlglot import expressions as exp

from app.core.semantic import SemanticModel


def _resolve_period(
    time_range: str | None, nl_lower: str, today: date | None = None
) -> dict[str, str] | None:
    today = today or date.today()
    tr = (time_range or "").lower().strip()

    def fmt(d: date) -> str:
        return d.isoformat()

    if tr in {"previous_week", "last_week", "прошлая неделя", "прошлая_неделя", "lastweek"}:
        weekday = today.weekday()
        this_monday = today - timedelta(days=weekday)
        prev_monday = this_monday - timedelta(days=7)
        prev_sunday = this_monday - timedelta(days=1)
        return {
            "label": f"прошлая календарная неделя (Пн {fmt(prev_monday)} — Вс {fmt(prev_sunday)})",
            "start": fmt(prev_monday),
            "end": fmt(prev_sunday),
        }

    if tr in {"this_week", "current_week"}:
        weekday = today.weekday()
        this_monday = today - timedelta(days=weekday)
        return {
            "label": f"текущая неделя (Пн {fmt(this_monday)} — {fmt(today)})",
            "start": fmt(this_monday),
            "end": fmt(today),
        }

    if tr in {"last_7_days", "rolling_7d", "последние 7 дней"}:
        start = today - timedelta(days=7)
        return {
            "label": f"скользящие последние 7 дней ({fmt(start)} — {fmt(today)})",
            "start": fmt(start),
            "end": fmt(today),
        }

    if tr in {"last_30_days", "rolling_30d", "последние 30 дней"}:
        start = today - timedelta(days=30)
        return {
            "label": f"скользящие последние 30 дней ({fmt(start)} — {fmt(today)})",
            "start": fmt(start),
            "end": fmt(today),
        }

    if tr in {"previous_month", "last_month", "прошлый месяц"}:
        first_of_this = today.replace(day=1)
        last_of_prev = first_of_this - timedelta(days=1)
        first_of_prev = last_of_prev.replace(day=1)
        return {
            "label": f"прошлый календарный месяц ({fmt(first_of_prev)} — {fmt(last_of_prev)})",
            "start": fmt(first_of_prev),
            "end": fmt(last_of_prev),
        }

    if tr in {"yesterday", "вчера"}:
        d = today - timedelta(days=1)
        return {"label": f"вчера ({fmt(d)})", "start": fmt(d), "end": fmt(d)}

    if tr in {"today", "сегодня"}:
        return {"label": f"сегодня ({fmt(today)})", "start": fmt(today), "end": fmt(today)}

    if "прошлую неделю" in nl_lower or "прошлой неделе" in nl_lower:
        return _resolve_period("previous_week", "", today)
    if "за последние 7 дней" in nl_lower or "последние 7" in nl_lower:
        return _resolve_period("last_7_days", "", today)
    if "за последние 30 дней" in nl_lower or "последние 30" in nl_lower:
        return _resolve_period("last_30_days", "", today)
    if "прошлый месяц" in nl_lower or "за прошлый месяц" in nl_lower:
        return _resolve_period("previous_month", "", today)
    if "вчера" in nl_lower:
        return _resolve_period("yesterday", "", today)
    if "сегодня" in nl_lower:
        return _resolve_period("today", "", today)

    return None


def _tables_used(sql: str) -> list[str]:
    try:
        tree = sqlglot.parse_one(sql, read="postgres")
    except Exception:
        return []
    cte_names: set[str] = set()
    for cte in tree.find_all(exp.CTE):
        a = cte.alias_or_name
        if a:
            cte_names.add(a.lower())
    out: list[str] = []
    seen: set[str] = set()
    for t in tree.find_all(exp.Table):
        name = t.name
        if not name:
            continue
        if name.lower() in cte_names:
            continue
        if name.lower() in seen:
            continue
        out.append(name)
        seen.add(name.lower())
    return out


def _measure_formulas(used_metrics: list[str], semantic: SemanticModel) -> list[dict[str, str]]:
    if not used_metrics:
        return []

    formula_index: dict[str, dict[str, str]] = {}
    for fact in semantic.facts.values():
        for m in fact.measures:
            formula_index.setdefault(
                m.name.lower(),
                {"name": m.name, "formula": m.expr, "source": fact.table},
            )
    for mname, metric in semantic.metrics.items():
        formula_index.setdefault(
            mname.lower(),
            {
                "name": mname,
                "formula": metric.expr,
                "source": "(вычисляется на лету)",
            },
        )

    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_name in used_metrics:
        key = raw_name.lower()
        if key in seen:
            continue
        entry = formula_index.get(key)
        if entry is not None:
            out.append(entry)
            seen.add(key)
    return out


def build_interpretation(
    nl_question: str,
    sql: str,
    explainer: dict[str, Any],
    semantic: SemanticModel,
    today: date | None = None,
) -> dict[str, Any]:
    nl_lower = nl_question.lower()
    period = _resolve_period(explainer.get("time_range"), nl_lower, today=today)
    tables = _tables_used(sql)
    formulas = _measure_formulas(list(explainer.get("used_metrics") or []), semantic)
    dimensions = list(explainer.get("used_dimensions") or [])

    parts: list[str] = []
    parts.append(f"Вопрос пользователя: «{nl_question.strip()}»")
    if formulas:
        for f in formulas:
            parts.append(
                f"Метрика «{f['name']}» считается как: `{f['formula']}` (источник: `{f['source']}`)."
            )
    elif explainer.get("used_metrics"):
        parts.append(f"Метрики: {', '.join(explainer['used_metrics'])}.")
    if dimensions:
        parts.append(f"Разрезы: {', '.join(dimensions)}.")
    if period:
        parts.append(f"Период: {period['label']}.")
    if tables:
        parts.append(f"Таблицы-источники: {', '.join(f'`{t}`' for t in tables)}.")

    structured_summary = " ".join(parts)
    llm_summary = (explainer.get("explanation_ru") or "").strip()

    return {
        "period": period,
        "tables": tables,
        "formulas": formulas,
        "dimensions": dimensions,
        "summary_ru": structured_summary,
        "llm_summary_ru": llm_summary,
    }
