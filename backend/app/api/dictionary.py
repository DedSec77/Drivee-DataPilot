from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.auth import require_api_token
from app.core.semantic import get_semantic

router = APIRouter(dependencies=[Depends(require_api_token)])


@router.get("/dictionary")
def get_dictionary() -> dict[str, Any]:
    sem = get_semantic()

    entities: list[dict[str, Any]] = []
    for name, ent in sem.entities.items():
        synonyms = ent.get("synonyms") or {}
        roles = ent.get("roles") or {}
        entities.append(
            {
                "name": name,
                "table": ent.get("table"),
                "key": ent.get("key"),
                "label_column": ent.get("label_column"),
                "synonyms_ru": list(synonyms.get("ru", [])),
                "synonyms_en": list(synonyms.get("en", [])),
                "pii": bool(ent.get("pii", False)),
                "pii_columns": list(ent.get("pii_columns", [])),
                "roles_allow": list(roles.get("allow", [])),
                "roles_deny": list(roles.get("deny", [])),
            }
        )

    facts: list[dict[str, Any]] = []
    for fname, fact in sem.facts.items():
        facts.append(
            {
                "name": fname,
                "table": fact.table,
                "grain": fact.grain,
                "time_column": fact.time_column,
                "require_time_filter": fact.require_time_filter,
                "foreign_keys": dict(fact.foreign_keys),
                "measures": [
                    {
                        "name": m.name,
                        "expr": m.expr,
                        "synonyms_ru": list(m.synonyms_ru),
                    }
                    for m in fact.measures
                ],
                "dimensions": [
                    {
                        "name": d.name,
                        "expr": d.expr,
                        "join": d.join,
                        "synonyms_ru": list(d.synonyms_ru),
                    }
                    for d in fact.dimensions
                ],
            }
        )

    metrics = [
        {
            "name": m.name,
            "expr": m.expr,
            "label_ru": m.label_ru,
            "synonyms_ru": list(m.synonyms_ru),
        }
        for m in sem.metrics.values()
    ]

    policies = {
        "deny_tables": sorted(sem.policies.deny_tables),
        "require_time_filter_tables": sorted(sem.policies.require_time_filter_tables),
        "default_limit": sem.policies.default_limit,
        "max_joins": sem.policies.max_joins,
        "max_total_cost": sem.policies.max_total_cost,
        "max_plan_rows": sem.policies.max_plan_rows,
        "pii_columns_by_role": {role: list(cols) for role, cols in sem.policies.pii_columns_by_role.items()},
    }

    return {
        "domain": sem.raw.get("domain"),
        "version": sem.raw.get("version"),
        "description": sem.raw.get("description"),
        "entities": entities,
        "facts": facts,
        "metrics": metrics,
        "policies": policies,
        "time_expressions_ru": dict(sem.time_expressions_ru),
        "cities_canonical_ru": dict(sem.cities_canonical_ru),
        "stats": {
            "entities": len(entities),
            "facts": len(facts),
            "measures": sum(len(f["measures"]) for f in facts),
            "dimensions": sum(len(f["dimensions"]) for f in facts),
            "metrics": len(metrics),
            "time_expressions": len(sem.time_expressions_ru),
            "cities_canonical": len(sem.cities_canonical_ru),
        },
    }


@router.get("/value_links/stats")
def get_value_links_stats() -> dict[str, Any]:
    from app.core.value_linker import get_value_linker

    linker = get_value_linker()
    sem = get_semantic()
    return {
        "indexed": linker.stats,
        "total": sum(linker.stats.values()),
        "columns": [
            {
                "alias": c.alias,
                "table": c.table,
                "column": c.column,
                "qualified": f"{c.table}.{c.column}",
                "synonyms_count": sum(len(v) for v in c.synonyms.values()),
                "synonyms_from": c.synonyms_from,
                "max_distinct": c.max_distinct,
            }
            for c in sem.value_linking_columns
        ],
    }


class _ValueLinkProbeRequest(BaseModel):
    question: str
    max_links: int = 8


@router.post("/value_links/probe")
def probe_value_links(req: _ValueLinkProbeRequest) -> dict[str, Any]:
    from app.core.value_linker import get_value_linker

    linker = get_value_linker()
    links = linker.link(req.question, max_links=req.max_links)
    return {
        "question": req.question,
        "links": [
            {
                "token": link.token,
                "column": link.column,
                "alias": link.alias,
                "value": link.db_value,
                "method": link.method,
                "score": round(1.0 - link.distance, 3),
            }
            for link in links
        ],
    }
