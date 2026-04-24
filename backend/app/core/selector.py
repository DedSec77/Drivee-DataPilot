from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import sqlglot
from sqlglot import expressions as exp

from app.core.guardrails import GuardResult
from app.core.llm import LLMCandidate

if TYPE_CHECKING:
    from app.core.voting import VotingResult


@dataclass
class ScoredCandidate:
    llm: LLMCandidate
    guard: GuardResult | None
    guard_error: str | None
    score: float
    components: dict[str, float]


def _ast_fingerprint(sql: str) -> str:
    try:
        tree = sqlglot.parse_one(sql, read="postgres")
    except Exception:
        return ""
    return tree.sql(dialect="postgres", normalize=True, pretty=False)


def _self_consistency(candidates: list[LLMCandidate]) -> list[float]:
    fps = [_ast_fingerprint(c.sql or "") for c in candidates]
    scores: list[float] = []
    for fp in fps:
        if not fp:
            scores.append(0.0)
            continue
        matches = sum(1 for other in fps if other and other == fp)
        scores.append(matches / max(1, len(fps)))
    return scores


def _schema_relevance(sql: str | None, retrieved_columns: set[str]) -> float:
    if not sql or not retrieved_columns:
        return 0.5
    try:
        tree = sqlglot.parse_one(sql, read="postgres")
    except Exception:
        return 0.0
    cols = {c.name.lower() for c in tree.find_all(exp.Column)}
    if not cols:
        return 0.5
    overlap = cols & {c.lower() for c in retrieved_columns}
    return min(1.0, len(overlap) / max(1, len(cols) * 0.5))


def _simplicity(sql: str | None) -> float:
    if not sql:
        return 0.0
    try:
        tree = sqlglot.parse_one(sql, read="postgres")
    except Exception:
        return 0.0
    joins = len(list(tree.find_all(exp.Join)))
    return 1.0 - min(1.0, joins / 5.0)


_TIME_HINT_COLS = {"trip_start_ts", "trip_end_ts", "booking_ts", "cancellation_ts"}


def _has_time_filter_signal(sql: str | None) -> float:
    if not sql:
        return 0.5
    try:
        tree = sqlglot.parse_one(sql, read="postgres")
    except Exception:
        return 0.5
    tables = {t.name.lower() for t in tree.find_all(exp.Table)}
    if "fct_trips" not in tables:
        return 1.0
    for where in tree.find_all(exp.Where):
        cols = {c.name.lower() for c in where.find_all(exp.Column)}
        if cols & _TIME_HINT_COLS:
            return 1.0
    return 0.4


def _execution_consensus_for(
    candidate_idx: int,
    voting: VotingResult | None,
) -> float:
    if voting is None or voting.successful_count == 0:
        return 0.0
    trace = voting.trace_for(candidate_idx)
    if trace is None or trace.error is not None or not trace.fingerprint:
        return 0.0
    bucket = voting.bucket_sizes.get(trace.fingerprint, 0)
    return bucket / voting.successful_count


def score_candidates(
    candidates: list[LLMCandidate],
    guard_results: list[tuple[GuardResult | None, str | None]],
    retrieved_columns: set[str],
    *,
    voting_result: VotingResult | None = None,
) -> list[ScoredCandidate]:
    sc = _self_consistency(candidates)
    use_voting = voting_result is not None and voting_result.successful_count > 0

    out: list[ScoredCandidate] = []
    for i, cand in enumerate(candidates):
        guard_ok = guard_results[i][0] is not None and guard_results[i][1] is None
        components: dict[str, float] = {
            "self_consistency": sc[i],
            "schema_relevance": _schema_relevance(cand.sql, retrieved_columns),
            "explain_passed": 1.0 if guard_ok else 0.0,
            "simplicity": _simplicity(cand.sql),
            "time_filter_ok": _has_time_filter_signal(cand.sql),
            "llm_self_conf": max(0.0, min(1.0, cand.confidence)),
        }
        if use_voting:
            components["execution_consensus"] = _execution_consensus_for(i, voting_result)
            score = (
                0.30 * components["execution_consensus"]
                + 0.15 * components["self_consistency"]
                + 0.15 * components["schema_relevance"]
                + 0.15 * components["explain_passed"]
                + 0.08 * components["simplicity"]
                + 0.08 * components["time_filter_ok"]
                + 0.09 * components["llm_self_conf"]
            )
        else:
            score = (
                0.35 * components["self_consistency"]
                + 0.18 * components["schema_relevance"]
                + 0.17 * components["explain_passed"]
                + 0.10 * components["simplicity"]
                + 0.10 * components["time_filter_ok"]
                + 0.10 * components["llm_self_conf"]
            )
        out.append(
            ScoredCandidate(
                llm=cand,
                guard=guard_results[i][0],
                guard_error=guard_results[i][1],
                score=score,
                components=components,
            )
        )

    return out


def pick_best(
    scored: list[ScoredCandidate],
    threshold: float,
) -> tuple[ScoredCandidate | None, bool]:
    if not scored:
        return None, True
    best = max(scored, key=lambda x: x.score)
    if best.guard is None or best.guard_error is not None:
        return best, True
    return best, best.score < threshold


def to_explainer(scored: ScoredCandidate, rules_applied: list[str] | None = None) -> dict[str, Any]:
    return {
        "confidence": round(scored.score, 3),
        "components": {k: round(v, 3) for k, v in scored.components.items()},
        "used_metrics": scored.llm.used_metrics,
        "used_dimensions": scored.llm.used_dimensions,
        "time_range": scored.llm.time_range,
        "explanation_ru": scored.llm.explanation_ru,
        "guard_rules_applied": rules_applied or (scored.guard.applied_rules if scored.guard else []),
        "explain_cost": scored.guard.est_cost if scored.guard else None,
        "explain_rows": scored.guard.est_rows if scored.guard else None,
    }
