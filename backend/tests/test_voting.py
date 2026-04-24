from __future__ import annotations

from decimal import Decimal

import pytest

pytest.importorskip("psycopg")
pytest.importorskip("sqlalchemy")
pytest.importorskip("sqlglot")

from app.core import voting
from app.core.guardrails import GuardResult
from app.core.llm import LLMCandidate
from app.core.selector import ScoredCandidate
from app.core.voting import (
    ExecutionTrace,
    execute_and_vote,
    result_fingerprint,
    voting_summary_for_log,
)


def test_fingerprint_stable_across_row_order():
    cols = ["city", "n"]
    a = result_fingerprint(cols, [("Москва", 10), ("СПб", 5)])
    b = result_fingerprint(cols, [("СПб", 5), ("Москва", 10)])
    assert a == b


def test_fingerprint_distinguishes_column_order():
    a = result_fingerprint(["city", "n"], [("Москва", 10)])
    b = result_fingerprint(["n", "city"], [(10, "Москва")])
    assert a != b


def test_fingerprint_decimal_rounding_2dp():
    a = result_fingerprint(["x"], [(Decimal("12.345"),)])
    b = result_fingerprint(["x"], [(Decimal("12.346"),)])
    assert a == b


def test_fingerprint_decimal_rounding_separates_pennies():
    a = result_fingerprint(["x"], [(Decimal("12.34"),)])
    b = result_fingerprint(["x"], [(Decimal("12.36"),)])
    assert a != b


def test_fingerprint_null_safe():
    a = result_fingerprint(["x"], [(None,)])
    b = result_fingerprint(["x"], [(None,)])
    c = result_fingerprint(["x"], [("",)])
    assert a == b
    assert a != c


def test_fingerprint_empty_result_is_stable():
    a = result_fingerprint(["x"], [])
    b = result_fingerprint(["x"], [])
    assert a == b
    assert a != ""


def test_fingerprint_str_strip():
    a = result_fingerprint(["c"], [("Москва",)])
    b = result_fingerprint(["c"], [("  Москва  ",)])
    assert a == b


def _mk_candidate(idx: int, sql: str, score: float = 0.5) -> ScoredCandidate:
    llm = LLMCandidate(
        sql=sql,
        clarify=None,
        raw="",
        used_metrics=[],
        used_dimensions=[],
        time_range=None,
        confidence=0.5,
        explanation_ru="",
    )
    guard = GuardResult(safe_sql=sql, applied_rules=[])
    return ScoredCandidate(
        llm=llm,
        guard=guard,
        guard_error=None,
        score=score,
        components={},
    )


def _mk_failed_candidate(idx: int) -> ScoredCandidate:
    llm = LLMCandidate(
        sql=None,
        clarify=None,
        raw="",
        used_metrics=[],
        used_dimensions=[],
        time_range=None,
        confidence=0.0,
        explanation_ru="",
    )
    return ScoredCandidate(
        llm=llm,
        guard=None,
        guard_error="GUARD_FAIL",
        score=0.1,
        components={},
    )


def _patch_execute(
    monkeypatch,
    sql_to_result: dict[str, tuple[list[str], list[tuple], str | None]],
):
    def fake(idx: int, sql: str, _timeout_ms: int) -> ExecutionTrace:
        cols, rows, err = sql_to_result[sql]
        if err is not None:
            return ExecutionTrace(
                candidate_idx=idx,
                safe_sql=sql,
                fingerprint="",
                columns=(),
                rows=(),
                row_count=0,
                exec_ms=1,
                error=err,
            )
        fp = result_fingerprint(cols, rows)
        return ExecutionTrace(
            candidate_idx=idx,
            safe_sql=sql,
            fingerprint=fp,
            columns=tuple(cols),
            rows=tuple(rows),
            row_count=len(rows),
            exec_ms=1,
            error=None,
        )

    monkeypatch.setattr(voting, "_execute_one", fake)


def test_majority_wins_over_score(monkeypatch):
    sql_a = "SELECT 1 AS x"
    sql_b = "SELECT 2 AS x"
    sql_c = "SELECT 1 + 0 AS x"

    cands = [
        _mk_candidate(0, sql_a, score=0.40),
        _mk_candidate(1, sql_b, score=0.85),
        _mk_candidate(2, sql_c, score=0.50),
    ]
    _patch_execute(
        monkeypatch,
        {
            sql_a: (["x"], [(1,)], None),
            sql_b: (["x"], [(2,)], None),
            sql_c: (["x"], [(1,)], None),
        },
    )

    res = execute_and_vote(cands, timeout_s=2.0)
    assert res.winner_idx in (0, 2)

    assert res.consensus_strength == pytest.approx(2 / 3)

    assert res.winner_idx != 1


def test_tiebreak_by_score_when_buckets_equal(monkeypatch):
    sql_a = "SELECT 1"
    sql_b = "SELECT 2"
    cands = [
        _mk_candidate(0, sql_a, score=0.30),
        _mk_candidate(1, sql_b, score=0.70),
    ]
    _patch_execute(
        monkeypatch,
        {
            sql_a: (["?column?"], [(1,)], None),
            sql_b: (["?column?"], [(2,)], None),
        },
    )

    res = execute_and_vote(cands, timeout_s=2.0)
    assert res.winner_idx == 1
    assert res.consensus_strength == 0.5


def test_dedup_same_sql_counts_as_two_votes(monkeypatch):
    sql_dup = "SELECT 1 AS x"
    sql_other = "SELECT 2 AS x"
    cands = [
        _mk_candidate(0, sql_dup, score=0.5),
        _mk_candidate(1, sql_dup, score=0.5),
        _mk_candidate(2, sql_other, score=0.9),
    ]
    call_count = {"n": 0}

    def fake(idx, sql, _t):
        call_count["n"] += 1
        if sql == sql_dup:
            cols, rows = ["x"], [(1,)]
        else:
            cols, rows = ["x"], [(2,)]
        return ExecutionTrace(
            candidate_idx=idx,
            safe_sql=sql,
            fingerprint=result_fingerprint(cols, rows),
            columns=tuple(cols),
            rows=tuple(rows),
            row_count=len(rows),
            exec_ms=1,
            error=None,
        )

    monkeypatch.setattr(voting, "_execute_one", fake)

    res = execute_and_vote(cands, timeout_s=2.0)
    assert call_count["n"] == 2
    assert res.consensus_strength == pytest.approx(2 / 3)
    assert res.winner_idx in (0, 1)


def test_partial_failure_voting_works_on_successes(monkeypatch):
    sql_ok1, sql_ok2, sql_bad = "SELECT 1", "SELECT 1+0", "BAD SQL"
    cands = [
        _mk_candidate(0, sql_ok1, score=0.5),
        _mk_candidate(1, sql_ok2, score=0.6),
        _mk_candidate(2, sql_bad, score=0.9),
    ]
    _patch_execute(
        monkeypatch,
        {
            sql_ok1: (["x"], [(1,)], None),
            sql_ok2: (["x"], [(1,)], None),
            sql_bad: ([], [], "ProgrammingError: syntax"),
        },
    )

    res = execute_and_vote(cands, timeout_s=2.0)
    assert res.winner_idx in (0, 1)
    assert res.consensus_strength == 1.0
    assert res.successful_count == 2


def test_all_fail_returns_no_winner(monkeypatch):
    sql_a, sql_b = "BAD A", "BAD B"
    cands = [
        _mk_candidate(0, sql_a),
        _mk_candidate(1, sql_b),
    ]
    _patch_execute(
        monkeypatch,
        {
            sql_a: ([], [], "DB error A"),
            sql_b: ([], [], "DB error B"),
        },
    )

    res = execute_and_vote(cands, timeout_s=2.0)
    assert res.winner_idx is None
    assert res.bucket_sizes == {}
    assert res.consensus_strength == 0.0
    assert "failed to execute" in res.rationale


def test_no_executable_candidates_returns_empty():
    cands = [_mk_failed_candidate(0), _mk_failed_candidate(1)]
    res = execute_and_vote(cands, timeout_s=2.0)
    assert res.winner_idx is None
    assert res.traces == []
    assert "no guard-passing" in res.rationale


def test_max_executions_caps_work(monkeypatch):
    sqls = [f"SELECT {i}" for i in range(5)]
    cands = [_mk_candidate(i, sqls[i], score=0.5) for i in range(5)]
    _patch_execute(monkeypatch, {s: (["x"], [(i,)], None) for i, s in enumerate(sqls)})

    res = execute_and_vote(cands, timeout_s=2.0, max_executions=3)

    assert len(res.traces) == 3
    executed_idxs = sorted(t.candidate_idx for t in res.traces)
    assert executed_idxs == [0, 1, 2]


def test_winner_trace_helper(monkeypatch):
    sql = "SELECT 1"
    cands = [_mk_candidate(0, sql)]
    _patch_execute(monkeypatch, {sql: (["x"], [(1,)], None)})
    res = execute_and_vote(cands, timeout_s=2.0)
    wt = res.winner_trace
    assert wt is not None
    assert wt.candidate_idx == 0
    assert wt.row_count == 1
    assert wt.error is None


def test_voting_summary_for_log_serializable(monkeypatch):
    import json

    sql = "SELECT 1"
    cands = [_mk_candidate(0, sql), _mk_candidate(1, sql)]
    _patch_execute(monkeypatch, {sql: (["x"], [(1,)], None)})
    res = execute_and_vote(cands, timeout_s=2.0)
    payload = voting_summary_for_log(res)
    encoded = json.dumps(payload)
    assert "bucket_sizes" in encoded
    assert payload["consensus_strength"] == 1.0
    assert payload["successful_count"] == 2
