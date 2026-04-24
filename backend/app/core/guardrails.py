from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import sqlglot
from sqlglot import expressions as exp


class GuardError(Exception):
    def __init__(self, code: str, message: str, user_hint_ru: str):
        super().__init__(message)
        self.code = code
        self.user_hint_ru = user_hint_ru

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "error": str(self), "hint_ru": self.user_hint_ru}


@dataclass
class GuardConfig:
    allowed_tables: set[str]
    deny_tables: set[str]
    forbidden_columns: set[str]
    require_time_filter_tables: set[str]
    time_columns_by_table: dict[str, str]
    max_joins: int = 5
    max_total_cost: float = 1e7
    max_plan_rows: int = 10_000_000
    default_limit: int = 500

    cities_canonical: dict[str, str] | None = None


@dataclass
class GuardResult:
    safe_sql: str
    applied_rules: list[str]
    est_cost: float | None = None
    est_rows: int | None = None


def _tables(tree: exp.Expression) -> set[str]:
    cte_names: set[str] = set()
    for cte in tree.find_all(exp.CTE):
        alias = cte.alias_or_name
        if alias:
            cte_names.add(alias)
    return {t.name for t in tree.find_all(exp.Table) if t.name not in cte_names}


def _has_time_filter(tree: exp.Expression, time_cols: set[str]) -> bool:
    if not time_cols:
        return False
    target = {c.lower() for c in time_cols}
    for where in tree.find_all(exp.Where):
        cols = {c.name.lower() for c in where.find_all(exp.Column)}
        if cols & target:
            return True
    return False


_AGG_FUNCS = {"count", "sum", "avg", "min", "max", "stddev", "variance"}

_EMPTY_RANGE_PAIRS: frozenset[frozenset[type[exp.Expression]]] = frozenset(
    {
        frozenset({exp.GTE, exp.LT}),
        frozenset({exp.GT, exp.LTE}),
        frozenset({exp.GT, exp.LT}),
    }
)


def _column_key(node: exp.Expression) -> tuple[str, str] | None:
    if not isinstance(node, exp.Column):
        return None
    table = (node.table or "").lower()
    return table, node.name.lower()


def _structurally_equal(a: exp.Expression, b: exp.Expression) -> bool:
    try:
        return a.sql(dialect="postgres", normalize=True) == b.sql(dialect="postgres", normalize=True)
    except Exception:
        return False


def _check_empty_range(tree: exp.Select, applied: list[str]) -> None:
    boundaries: dict[tuple[str, str], list[tuple[type[exp.Expression], exp.Expression]]] = {}
    for predicate in (*tree.find_all(exp.Where), *tree.find_all(exp.Join)):
        for cmp in predicate.find_all((exp.GT, exp.GTE, exp.LT, exp.LTE)):
            left, right = cmp.this, cmp.expression
            key = _column_key(left)
            other = right
            if key is None:
                key = _column_key(right)
                other = left
                if key is None:
                    continue
            boundaries.setdefault(key, []).append((type(cmp), other))

    for col, items in boundaries.items():
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                op_a, rhs_a = items[i]
                op_b, rhs_b = items[j]
                if frozenset({op_a, op_b}) not in _EMPTY_RANGE_PAIRS:
                    continue
                if not _structurally_equal(rhs_a, rhs_b):
                    continue
                col_label = f"{col[0]}.{col[1]}" if col[0] else col[1]
                raise GuardError(
                    "EMPTY_RANGE",
                    f"empty interval on {col_label}: both bounds equal {rhs_a.sql(dialect='postgres')!r}",
                    "Левый и правый край интервала по времени совпадают — "
                    "запрос гарантированно вернёт 0 строк. Это типично для "
                    "«на этой неделе»: правая граница должна быть `now()`, "
                    "а не `date_trunc('week', now())`.",
                )
    applied.append("check_empty_range")


def _is_aggregate_only_select(tree: exp.Expression) -> bool:
    if not isinstance(tree, exp.Select):
        return False
    if tree.args.get("group"):
        return True
    if tree.args.get("having"):
        return True

    select_exprs = tree.args.get("expressions") or []
    if not select_exprs:
        return False

    has_window = any(list(e.find_all(exp.Window)) for e in select_exprs)
    if has_window:
        return False

    for e in select_exprs:
        target = e.unalias() if isinstance(e, exp.Alias) else e
        if isinstance(target, (exp.Star, exp.Column)):
            return False
        agg_inside = list(target.find_all(exp.AggFunc)) or [
            f for f in target.find_all(exp.Func) if f.key.lower() in _AGG_FUNCS
        ]
        if not agg_inside and not isinstance(target, (exp.Literal, exp.Cast)):
            return False
    return True


def _strip_comments(sql: str) -> str:
    out: list[str] = []
    i = 0
    n = len(sql)
    in_single = False
    in_double = False
    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""

        if not in_single and not in_double:
            if ch == "-" and nxt == "-":
                j = sql.find("\n", i)
                if j == -1:
                    break
                i = j
                continue
            if ch == "/" and nxt == "*":
                j = sql.find("*/", i + 2)
                if j == -1:
                    break
                i = j + 2
                continue
            if ch == "'":
                in_single = True
            elif ch == '"':
                in_double = True
        else:
            if in_single and ch == "'":
                in_single = False
            elif in_double and ch == '"':
                in_double = False

        out.append(ch)
        i += 1
    return "".join(out).strip()


_FORBIDDEN_STMT_TYPES = (
    exp.Drop,
    exp.Delete,
    exp.Update,
    exp.Insert,
    exp.Alter,
    exp.Create,
    exp.Merge,
)


def _parse_select(sql: str) -> exp.Select:
    try:
        tree = sqlglot.parse_one(sql, read="postgres")
    except sqlglot.errors.ParseError as e:
        raise GuardError(
            "PARSE",
            str(e),
            "Не удалось разобрать SQL. Попробуйте переформулировать.",
        ) from e

    if tree is None:
        raise GuardError("EMPTY", "Empty query", "Пустой запрос.")

    if not isinstance(tree, exp.Select):
        raise GuardError(
            "NON_SELECT",
            f"Only SELECT allowed, got {type(tree).__name__}",
            "Изменяющие запросы (DROP / UPDATE / DELETE / INSERT) запрещены.",
        )

    for bad in _FORBIDDEN_STMT_TYPES:
        if list(tree.find_all(bad)):
            raise GuardError(
                "FORBIDDEN_STMT",
                f"Forbidden statement {bad.__name__}",
                "Запрос содержит запрещённую операцию.",
            )
    return tree


def _check_table_acl(tree: exp.Select, cfg: GuardConfig, applied: list[str]) -> set[str]:
    tables = _tables(tree)
    if not tables:
        raise GuardError("NO_TABLES", "Query has no FROM tables", "Запрос не обращается к таблицам.")

    denied = tables & cfg.deny_tables
    if denied:
        raise GuardError(
            "DENY_TABLE",
            f"Denied tables: {denied}",
            f"Запрос обращается к защищённым таблицам: {', '.join(denied)}",
        )
    applied.append("check_deny_tables")

    if cfg.allowed_tables:
        unknown = tables - cfg.allowed_tables
        if unknown:
            raise GuardError(
                "UNKNOWN_TABLE",
                f"Unknown tables: {unknown}",
                f"Неизвестные таблицы: {', '.join(unknown)}. Используйте семантический слой.",
            )
        applied.append("check_allowed_tables")
    return tables


def _check_pii(tree: exp.Select, cfg: GuardConfig, applied: list[str]) -> None:
    used_cols = {c.name.lower() for c in tree.find_all(exp.Column)}
    bad_cols = used_cols & {c.lower() for c in cfg.forbidden_columns}
    if bad_cols:
        raise GuardError(
            "PII_COLUMN",
            f"PII columns: {bad_cols}",
            f"Колонки {', '.join(bad_cols)} содержат PII и недоступны вашей роли.",
        )
    applied.append("check_pii")


def _check_joins(tree: exp.Select, cfg: GuardConfig, applied: list[str]) -> None:
    joins = list(tree.find_all(exp.Join))
    if len(joins) > cfg.max_joins:
        raise GuardError(
            "TOO_MANY_JOINS",
            f"joins={len(joins)} max={cfg.max_joins}",
            f"Запрос слишком сложный (джоинов: {len(joins)}). Упростите формулировку.",
        )
    applied.append("check_joins")


def _check_time_filter(tree: exp.Select, cfg: GuardConfig, tables: set[str], applied: list[str]) -> None:
    needs_time = tables & cfg.require_time_filter_tables
    if not needs_time:
        return
    time_cols = {cfg.time_columns_by_table.get(t, "") for t in needs_time}
    time_cols.discard("")
    if not _has_time_filter(tree, time_cols):
        raise GuardError(
            "NO_TIME_FILTER",
            f"time filter missing for {needs_time}",
            "Нужен фильтр по времени (например, «за прошлую неделю» или «за последние 7 дней»).",
        )
    applied.append("check_time_filter")


def _canonicalise_cities(tree: exp.Select, cfg: GuardConfig, applied: list[str]) -> None:
    if not cfg.cities_canonical:
        return
    canon = {k.lower(): v for k, v in cfg.cities_canonical.items()}
    substituted = 0
    for lit in tree.find_all(exp.Literal):
        if not lit.is_string:
            continue
        raw_value = lit.this
        if not isinstance(raw_value, str):
            continue
        key = raw_value.strip().lower()
        replacement = canon.get(key)
        if replacement and replacement != raw_value:
            lit.replace(exp.Literal.string(replacement))
            substituted += 1
    if substituted:
        applied.append(f"canon_cities:{substituted}")


def _inject_rls(
    tree: exp.Select,
    user_ctx: dict[str, Any],
    tables: set[str],
    applied: list[str],
) -> None:
    allowed_cities: list[int] | None = user_ctx.get("allowed_city_ids")
    if allowed_cities is None or "fct_trips" not in tables:
        return
    rls_expr = exp.column("city_id").isin(*[exp.Literal.number(c) for c in allowed_cities])
    current_where = tree.args.get("where")
    if current_where:
        tree.set("where", exp.Where(this=exp.and_(current_where.this, rls_expr)))
    else:
        tree.set("where", exp.Where(this=rls_expr))
    applied.append("inject_rls_cities")


def _inject_limit(tree: exp.Select, cfg: GuardConfig, applied: list[str]) -> None:
    if tree.args.get("limit") or _is_aggregate_only_select(tree):
        return
    tree.set("limit", exp.Limit(expression=exp.Literal.number(cfg.default_limit)))
    applied.append("inject_limit")


def ast_validate(
    sql: str,
    cfg: GuardConfig,
    user_ctx: dict[str, Any] | None = None,
) -> tuple[exp.Select, list[str]]:
    user_ctx = user_ctx or {}
    applied: list[str] = []

    tree = _parse_select(_strip_comments(sql))
    tables = _check_table_acl(tree, cfg, applied)
    _check_pii(tree, cfg, applied)
    _check_joins(tree, cfg, applied)
    _check_time_filter(tree, cfg, tables, applied)

    _check_empty_range(tree, applied)
    _canonicalise_cities(tree, cfg, applied)
    _inject_rls(tree, user_ctx, tables, applied)
    _inject_limit(tree, cfg, applied)

    return tree, applied


def explain_cost(conn, safe_sql: str) -> tuple[float, int]:
    with conn.cursor() as cur:
        cur.execute(f"EXPLAIN (FORMAT JSON) {safe_sql}")
        row = cur.fetchone()
    plan = row[0][0]["Plan"] if row else {}
    return float(plan.get("Total Cost", 0.0)), int(plan.get("Plan Rows", 0))


def guard_sql(
    raw_sql: str,
    cfg: GuardConfig,
    user_ctx: dict[str, Any] | None = None,
    conn=None,
) -> GuardResult:
    cleaned = _strip_comments(raw_sql)
    tree, applied = ast_validate(cleaned, cfg, user_ctx)
    safe_sql = tree.sql(dialect="postgres")

    cost: float | None = None
    rows: int | None = None
    if conn is not None:
        try:
            cost, rows = explain_cost(conn, safe_sql)
        except Exception as e:
            raise GuardError("EXPLAIN_FAILED", str(e), "Не удалось проверить план запроса.") from e
        if cost > cfg.max_total_cost or rows > cfg.max_plan_rows:
            raise GuardError(
                "TOO_EXPENSIVE",
                f"cost={cost:.0f} rows={rows}",
                f"Запрос слишком тяжёлый (cost={cost:.0f}). Добавьте фильтр по времени или городу.",
            )
        applied.append("check_explain_cost")

    return GuardResult(safe_sql=safe_sql, applied_rules=applied, est_cost=cost, est_rows=rows)


def build_guard_config(semantic, role: str = "business_user") -> GuardConfig:
    pii_cols = set(semantic.policies.pii_columns_by_role.get(role, []))
    time_columns = {f.table: f.time_column for f in semantic.facts.values()}
    return GuardConfig(
        allowed_tables=semantic.allowed_tables,
        deny_tables=semantic.policies.deny_tables,
        forbidden_columns=pii_cols,
        require_time_filter_tables=semantic.policies.require_time_filter_tables,
        time_columns_by_table=time_columns,
        max_joins=semantic.policies.max_joins,
        max_total_cost=semantic.policies.max_total_cost,
        max_plan_rows=semantic.policies.max_plan_rows,
        default_limit=semantic.policies.default_limit,
        cities_canonical=semantic.cities_canonical_ru or None,
    )
