from __future__ import annotations

import concurrent.futures
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from loguru import logger

from app.core.selector import ScoredCandidate
from app.db.session import raw_psycopg
from eval.compare import canon_row


@dataclass(frozen=True)
class ExecutionTrace:
    candidate_idx: int
    safe_sql: str
    fingerprint: str
    columns: tuple[str, ...]
    rows: tuple[tuple, ...]
    row_count: int
    exec_ms: int
    error: str | None


@dataclass(frozen=True)
class VotingResult:
    winner_idx: int | None
    bucket_sizes: dict[str, int]
    traces: list[ExecutionTrace]
    consensus_strength: float
    rationale: str

    @property
    def winner_trace(self) -> ExecutionTrace | None:
        if self.winner_idx is None:
            return None
        for t in self.traces:
            if t.candidate_idx == self.winner_idx:
                return t
        return None

    @property
    def successful_count(self) -> int:
        return sum(1 for t in self.traces if t.error is None and t.fingerprint)

    def trace_for(self, candidate_idx: int) -> ExecutionTrace | None:
        for t in self.traces:
            if t.candidate_idx == candidate_idx:
                return t
        return None


def result_fingerprint(columns: list[str], rows: list[tuple]) -> str:
    canon = sorted(canon_row(r) for r in rows)
    payload = json.dumps(
        [list(columns), [list(c) for c in canon]],
        ensure_ascii=False,
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _execute_one(
    candidate_idx: int,
    safe_sql: str,
    statement_timeout_ms: int,
) -> ExecutionTrace:
    t0 = time.time()
    try:
        with raw_psycopg() as conn, conn.cursor() as cur:
            if statement_timeout_ms > 0:
                cur.execute(f"SET LOCAL statement_timeout = {statement_timeout_ms}")
            cur.execute(safe_sql)
            if cur.description is None:
                cols: list[str] = []
                rows: list[tuple] = []
            else:
                cols = [c.name for c in cur.description]
                rows = cur.fetchall()
        fp = result_fingerprint(cols, rows)
        return ExecutionTrace(
            candidate_idx=candidate_idx,
            safe_sql=safe_sql,
            fingerprint=fp,
            columns=tuple(cols),
            rows=tuple(tuple(r) for r in rows),
            row_count=len(rows),
            exec_ms=int((time.time() - t0) * 1000),
            error=None,
        )
    except Exception as e:
        return ExecutionTrace(
            candidate_idx=candidate_idx,
            safe_sql=safe_sql,
            fingerprint="",
            columns=(),
            rows=(),
            row_count=0,
            exec_ms=int((time.time() - t0) * 1000),
            error=f"{type(e).__name__}: {e}",
        )


def execute_and_vote(
    scored: list[ScoredCandidate],
    *,
    timeout_s: float = 5.0,
    max_executions: int = 5,
    max_parallel: int = 3,
) -> VotingResult:
    executable = [(i, c) for i, c in enumerate(scored) if c.guard is not None and c.guard.safe_sql]
    if not executable:
        return VotingResult(
            winner_idx=None,
            bucket_sizes={},
            traces=[],
            consensus_strength=0.0,
            rationale="no guard-passing candidates",
        )

    executable = executable[:max_executions]

    seen_sql: dict[str, int] = {}
    unique_jobs: list[tuple[int, str]] = []
    for idx, cand in executable:
        sql = cand.guard.safe_sql
        if sql not in seen_sql:
            seen_sql[sql] = idx
            unique_jobs.append((idx, sql))

    statement_timeout_ms = int(timeout_s * 1000)
    raw_traces: list[ExecutionTrace] = []

    with ThreadPoolExecutor(max_workers=min(len(unique_jobs), max_parallel)) as pool:
        futures = {
            pool.submit(_execute_one, idx, sql, statement_timeout_ms): (idx, sql) for idx, sql in unique_jobs
        }
        try:
            for fut in as_completed(futures, timeout=timeout_s + 1.0):
                raw_traces.append(fut.result())
        except concurrent.futures.TimeoutError:
            done_idxs = {t.candidate_idx for t in raw_traces}
            for fut, (idx, sql) in futures.items():
                if not fut.done() and idx not in done_idxs:
                    fut.cancel()
                    raw_traces.append(
                        ExecutionTrace(
                            candidate_idx=idx,
                            safe_sql=sql,
                            fingerprint="",
                            columns=(),
                            rows=(),
                            row_count=0,
                            exec_ms=int(timeout_s * 1000),
                            error="TimeoutError: vote-wide deadline exceeded",
                        )
                    )

    traces_by_sql = {t.safe_sql: t for t in raw_traces}
    full_traces: list[ExecutionTrace] = []
    for idx, cand in executable:
        sql = cand.guard.safe_sql
        prototype = traces_by_sql.get(sql)
        if prototype is None:
            continue
        if prototype.candidate_idx == idx:
            full_traces.append(prototype)
        else:
            full_traces.append(
                ExecutionTrace(
                    candidate_idx=idx,
                    safe_sql=sql,
                    fingerprint=prototype.fingerprint,
                    columns=prototype.columns,
                    rows=prototype.rows,
                    row_count=prototype.row_count,
                    exec_ms=prototype.exec_ms,
                    error=prototype.error,
                )
            )

    successful = [t for t in full_traces if t.error is None and t.fingerprint]
    if not successful:
        return VotingResult(
            winner_idx=None,
            bucket_sizes={},
            traces=full_traces,
            consensus_strength=0.0,
            rationale=f"all {len(full_traces)} candidate(s) failed to execute",
        )

    bucket_sizes: dict[str, int] = {}
    for t in successful:
        bucket_sizes[t.fingerprint] = bucket_sizes.get(t.fingerprint, 0) + 1

    largest_size = max(bucket_sizes.values())
    winning_fps = {fp for fp, sz in bucket_sizes.items() if sz == largest_size}

    candidates_in_winning_bucket = [
        (t, scored[t.candidate_idx]) for t in successful if t.fingerprint in winning_fps
    ]
    winner_trace, _ = max(
        candidates_in_winning_bucket,
        key=lambda pair: pair[1].score,
    )
    winner_idx = winner_trace.candidate_idx

    consensus = largest_size / len(successful)
    rationale = (
        f"{largest_size}/{len(successful)} candidate(s) agreed on result-set {winner_trace.fingerprint[:8]}"
    )
    if len(winning_fps) > 1:
        rationale += f"; {len(winning_fps)} buckets tied, picked best score"

    logger.info(
        f"[voting] buckets={bucket_sizes} winner_idx={winner_idx} "
        f"consensus={consensus:.2f} successful={len(successful)}"
    )

    return VotingResult(
        winner_idx=winner_idx,
        bucket_sizes=bucket_sizes,
        traces=full_traces,
        consensus_strength=consensus,
        rationale=rationale,
    )


def voting_summary_for_log(voting: VotingResult) -> dict[str, Any]:
    return {
        "winner_idx": voting.winner_idx,
        "bucket_sizes": voting.bucket_sizes,
        "consensus_strength": round(voting.consensus_strength, 3),
        "successful_count": voting.successful_count,
        "total_traces": len(voting.traces),
        "rationale": voting.rationale,
        "trace_ms": [t.exec_ms for t in voting.traces],
    }
