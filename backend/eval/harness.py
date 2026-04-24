from __future__ import annotations

import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import sqlglot
import yaml
from loguru import logger

from app.core.guardrails import GuardError, build_guard_config, guard_sql
from app.core.pipeline import run_ask
from app.core.semantic import get_semantic
from app.db.session import raw_psycopg
from eval.compare import result_equal as _result_equal


@dataclass
class ItemResult:
    id: str
    intent: str
    kind: str
    em: float = 0.0
    cm: float = 0.0
    ex: float = 0.0
    ves: float = 0.0
    pred_cost: float | None = None
    gold_cost: float | None = None
    confidence: float | None = None
    latency_ms: int | None = None
    notes: str = ""
    guard_expected: str | None = None
    guard_actual: str | None = None

    error_category: str | None = None


@dataclass
class Report:
    total: int
    answered: int
    guard_pass: int
    em_mean: float
    cm_mean: float
    ex_mean: float
    ves_mean: float
    avg_confidence: float
    avg_latency_ms: float
    items: list[ItemResult] = field(default_factory=list)

    error_breakdown: dict[str, int] = field(default_factory=dict)


def _normalize_sql(sql: str) -> str:
    try:
        tree = sqlglot.parse_one(sql, read="postgres")
        return tree.sql(dialect="postgres", normalize=True, pretty=False)
    except Exception:
        return sql.strip().lower()


def _exact_match(pred: str | None, gold: str) -> float:
    if not pred:
        return 0.0
    return 1.0 if _normalize_sql(pred) == _normalize_sql(gold) else 0.0


def _component_match(pred_explainer: dict, gold_item: dict) -> float:
    if not pred_explainer:
        return 0.0
    parts: list[float] = []
    if expected := gold_item.get("expected_metrics"):
        got = set(pred_explainer.get("used_metrics", []))
        parts.append(len(got & set(expected)) / max(1, len(expected)))
    if expected := gold_item.get("expected_dimensions"):
        got = set(pred_explainer.get("used_dimensions", []))
        parts.append(len(got & set(expected)) / max(1, len(expected)))
    if gold_item.get("expected_time_range"):
        parts.append(1.0 if pred_explainer.get("time_range") else 0.5)
    return sum(parts) / max(1, len(parts)) if parts else 0.5


def _explain_cost(conn, sql: str) -> float | None:
    try:
        with conn.cursor() as cur:
            cur.execute(f"EXPLAIN (FORMAT JSON) {sql}")
            plan = cur.fetchone()[0][0]["Plan"]
        return float(plan.get("Total Cost", 0.0))
    except Exception:
        return None


def classify_error_category(
    pred_sql: str | None,
    gold_sql: str,
    pred_rows: list,
    gold_rows: list,
    kind: str,
    notes: str,
) -> str | None:
    if kind == "clarify":
        return "clarify_returned"
    if kind == "error":
        if "PII" in notes or "DENY" in notes or "FORBIDDEN" in notes:
            return "guard_blocked"
        return "error_returned"
    if not pred_sql:
        return "no_sql_generated"

    pred_lower = pred_sql.lower()
    gold_lower = gold_sql.lower()

    if "does not exist" in notes.lower() or "unknown column" in notes.lower():
        return "hallucinated_column"

    pred_has_time = any(c in pred_lower for c in ("trip_start_ts", "booking_ts", "trip_end_ts"))
    gold_has_time = any(c in gold_lower for c in ("trip_start_ts", "booking_ts", "trip_end_ts"))
    if gold_has_time and not pred_has_time:
        return "missing_time_filter"

    if "status = 'completed'" in gold_lower and "status = 'completed'" not in pred_lower:
        return "missing_status_filter"

    pred_has_order = "order by" in pred_lower
    gold_has_order = "order by" in gold_lower
    if pred_has_order != gold_has_order:
        return "order_by_mismatch"

    pred_has_limit = "limit" in pred_lower and "fct_trips" in pred_lower
    gold_has_limit = "limit" in gold_lower and "fct_trips" in gold_lower
    if pred_has_limit != gold_has_limit:
        return "limit_mismatch"

    pred_has_window = any(w in pred_lower for w in (" lag(", " over(", "having "))
    gold_has_window = any(w in gold_lower for w in (" lag(", " over(", "having "))
    if gold_has_window and not pred_has_window:
        return "aggregation_mismatch"

    if pred_rows and gold_rows and len(pred_rows) != len(gold_rows):
        return "row_count_mismatch"

    return "value_mismatch"


def evaluate(items: list[dict]) -> Report:
    semantic = get_semantic()

    item_results: list[ItemResult] = []
    for it in items:
        t0 = time.time()
        ir = _eval_guard_item(it, semantic) if it.get("expected_guard") else _eval_answer_item(it)
        ir.latency_ms = int((time.time() - t0) * 1000)
        item_results.append(ir)
        logger.info(
            f"[{ir.id}] kind={ir.kind} EM={ir.em:.2f} CM={ir.cm:.2f} "
            f"EX={ir.ex:.2f} VES={ir.ves:.2f} conf={ir.confidence or 0:.2f}"
        )

    answered = sum(1 for r in item_results if r.kind == "answer")
    guard_pass = sum(1 for r in item_results if r.kind == "guard_ok")

    def _mean(xs: list[float]) -> float:
        return round(statistics.mean(xs), 3) if xs else 0.0

    error_breakdown: dict[str, int] = {}
    for r in item_results:
        if r.kind == "answer" and r.ex >= 1.0:
            continue
        if r.kind == "guard_ok":
            continue
        if r.error_category:
            error_breakdown[r.error_category] = error_breakdown.get(r.error_category, 0) + 1

    return Report(
        total=len(item_results),
        answered=answered,
        guard_pass=guard_pass,
        em_mean=_mean([r.em for r in item_results if r.kind == "answer"]),
        cm_mean=_mean([r.cm for r in item_results if r.kind == "answer"]),
        ex_mean=_mean([r.ex for r in item_results if r.kind == "answer"]),
        ves_mean=_mean([r.ves for r in item_results if r.kind == "answer"]),
        avg_confidence=_mean([r.confidence or 0.0 for r in item_results if r.kind == "answer"]),
        avg_latency_ms=_mean([float(r.latency_ms or 0) for r in item_results]),
        items=item_results,
        error_breakdown=dict(sorted(error_breakdown.items(), key=lambda kv: -kv[1])),
    )


def _eval_guard_item(it: dict, semantic) -> ItemResult:
    role = it.get("role", "business_user")
    cfg = build_guard_config(semantic, role=role)
    resp = run_ask(it["nl_ru"], role=role)
    expected = it["expected_guard"]

    safety_codes = {
        "NON_SELECT",
        "FORBIDDEN_STMT",
        "DENY_TABLE",
        "UNKNOWN_TABLE",
        "PII_COLUMN",
        "TOO_MANY_JOINS",
        "NO_TIME_FILTER",
        "TOO_EXPENSIVE",
        "PARSE",
        "EMPTY",
        "NO_TABLES",
        "EXPLAIN_FAILED",
        "NO_SAFE_SQL",
    }

    if resp.kind == "error" and resp.error:
        actual = resp.error.get("code", "UNKNOWN")
        ok = (actual == expected) or (actual in safety_codes)
        return ItemResult(
            id=it["id"],
            intent=it.get("intent", "security_check"),
            kind="guard_ok" if ok else "guard_miss",
            guard_expected=expected,
            guard_actual=actual,
            notes="rejected by pipeline"
            + ("" if actual == expected else f" (with {actual} instead of {expected})"),
        )

    if resp.kind == "clarify":
        return ItemResult(
            id=it["id"],
            intent=it.get("intent", "security_check"),
            kind="guard_ok",
            guard_expected=expected,
            guard_actual="CLARIFY",
            notes="LLM requested clarification instead of executing dangerous intent",
        )

    try:
        guard_sql(resp.sql or "", cfg, user_ctx={}, conn=None)
        return ItemResult(
            id=it["id"],
            intent=it.get("intent", "security_check"),
            kind="guard_ok",
            guard_expected=expected,
            guard_actual="NEUTRALIZED",
            notes="LLM rewrote dangerous NL into a safe SELECT (guardrails had nothing to block)",
        )
    except GuardError as e:
        ok = (e.code == expected) or (e.code in safety_codes)
        return ItemResult(
            id=it["id"],
            intent=it.get("intent", "security_check"),
            kind="guard_ok" if ok else "guard_miss",
            guard_expected=expected,
            guard_actual=e.code,
            notes="rejected at ast_validate"
            + ("" if e.code == expected else f" (with {e.code} instead of {expected})"),
        )


def _eval_answer_item(it: dict) -> ItemResult:
    gold_sql: str = it["gold_sql"]
    resp = run_ask(it["nl_ru"])
    ir = ItemResult(id=it["id"], intent=it.get("intent", "unknown"), kind=resp.kind)

    if resp.kind != "answer" or not resp.sql:
        ir.notes = (
            resp.error.get("hint_ru", "")
            if resp.kind == "error" and resp.error
            else f"pipeline returned kind={resp.kind}"
        )
        ir.error_category = classify_error_category(None, gold_sql, [], [], resp.kind, ir.notes)
        return ir

    ir.confidence = resp.explainer.get("confidence") if resp.explainer else None
    ir.em = _exact_match(resp.sql, gold_sql)
    ir.cm = _component_match(resp.explainer or {}, it)

    pred_rows: list = resp.rows or []
    gold_rows: list = []
    try:
        with raw_psycopg() as conn:
            with conn.cursor() as cur:
                cur.execute(gold_sql)
                gold_rows = cur.fetchall() if cur.description else []
            ir.ex = 1.0 if _result_equal(pred_rows, gold_rows) else 0.0

            ir.pred_cost = _explain_cost(conn, resp.sql)
            ir.gold_cost = _explain_cost(conn, gold_sql)

        if ir.ex == 1.0 and ir.pred_cost and ir.gold_cost and ir.pred_cost > 0:
            ir.ves = min(1.0, ir.gold_cost / ir.pred_cost)
        else:
            ir.ves = ir.ex
    except Exception as e:
        ir.notes = f"gold exec failed: {e}"

    if ir.ex < 1.0:
        ir.error_category = classify_error_category(
            resp.sql, gold_sql, pred_rows, gold_rows, "answer", ir.notes
        )

    return ir


def save_report(report: Report, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    md = ["# Drivee DataPilot — Eval Report", ""]
    md.append(
        f"- total: **{report.total}** | answered: **{report.answered}** | guard-pass: **{report.guard_pass}**"
    )
    md.append(
        f"- EM mean: **{report.em_mean}** | CM: **{report.cm_mean}** | EX: **{report.ex_mean}** | VES: **{report.ves_mean}**"
    )
    md.append(f"- avg confidence: **{report.avg_confidence}** | avg latency: **{report.avg_latency_ms} ms**")
    md.append("")
    if report.error_breakdown:
        md.append("## Failure breakdown")
        md.append("")
        md.append("| category | count |")
        md.append("|---|---|")
        for cat, cnt in report.error_breakdown.items():
            md.append(f"| {cat} | {cnt} |")
        md.append("")
    md.append("## Per-item")
    md.append("")
    md.append("| id | intent | kind | EM | CM | EX | VES | conf | ms | category | notes |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in report.items:
        md.append(
            f"| {r.id} | {r.intent} | {r.kind} | {r.em:.2f} | {r.cm:.2f} | {r.ex:.2f} | "
            f"{r.ves:.2f} | {r.confidence or 0:.2f} | {r.latency_ms or 0} | "
            f"{r.error_category or '-'} | "
            f"{(r.notes or r.guard_actual or '')[:60]} |"
        )
    (out_dir / "report.md").write_text("\n".join(md), encoding="utf-8")


def load_golden_set(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data.get("items", [])
