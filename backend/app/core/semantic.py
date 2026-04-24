from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.core.config import settings

_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _validate_identifier(name: str, *, field: str) -> str:
    if not isinstance(name, str) or not _IDENT_RE.fullmatch(name):
        raise ValueError(
            f"Недопустимый SQL-идентификатор в semantic.yaml: {field}={name!r}. "
            "Разрешены только имена, подходящие под ^[a-zA-Z_][a-zA-Z0-9_]*$."
        )
    return name


@dataclass
class Measure:
    name: str
    expr: str
    synonyms_ru: list[str] = field(default_factory=list)


@dataclass
class Dimension:
    name: str
    expr: str
    join: str | None = None
    synonyms_ru: list[str] = field(default_factory=list)


@dataclass
class Metric:
    name: str
    expr: str
    label_ru: str
    synonyms_ru: list[str] = field(default_factory=list)


@dataclass
class Fact:
    name: str
    table: str
    grain: str
    time_column: str
    require_time_filter: bool
    dimensions: list[Dimension]
    measures: list[Measure]
    foreign_keys: dict[str, str]


@dataclass
class Policies:
    deny_tables: set[str]
    require_time_filter_tables: set[str]
    default_limit: int
    max_joins: int
    max_total_cost: float
    max_plan_rows: int
    pii_columns_by_role: dict[str, list[str]]


@dataclass
class ValueLinkingColumn:
    alias: str
    table: str
    column: str
    synonyms: dict[str, list[str]]
    synonyms_from: str | None = None

    max_distinct: int = 2000


@dataclass
class SemanticModel:
    raw: dict[str, Any]
    entities: dict[str, dict[str, Any]]
    facts: dict[str, Fact]
    metrics: dict[str, Metric]
    policies: Policies
    time_expressions_ru: dict[str, str]
    cities_canonical_ru: dict[str, str]
    value_linking_columns: list[ValueLinkingColumn] = field(default_factory=list)

    @property
    def allowed_tables(self) -> set[str]:
        out: set[str] = set()
        for ent in self.entities.values():
            if t := ent.get("table"):
                out.add(t)
        for fact in self.facts.values():
            out.add(fact.table)
        return out

    @property
    def forbidden_columns_by_role(self) -> dict[str, set[str]]:
        return {role: {c.lower() for c in cols} for role, cols in self.policies.pii_columns_by_role.items()}

    def retrievable_items(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for name, ent in self.entities.items():
            for phrase in ent.get("synonyms", {}).get("ru", []) + ent.get("synonyms", {}).get("en", []):
                items.append(
                    {
                        "kind": "entity",
                        "name": name,
                        "phrase": phrase,
                        "payload": {"table": ent.get("table"), "key": ent.get("key")},
                    }
                )
        for fname, fact in self.facts.items():
            for m in fact.measures:
                for phrase in m.synonyms_ru + [m.name]:
                    items.append(
                        {
                            "kind": "measure",
                            "name": m.name,
                            "fact": fname,
                            "phrase": phrase,
                            "payload": {"expr": m.expr},
                        }
                    )
            for d in fact.dimensions:
                for phrase in d.synonyms_ru + [d.name]:
                    items.append(
                        {
                            "kind": "dimension",
                            "name": d.name,
                            "fact": fname,
                            "phrase": phrase,
                            "payload": {"expr": d.expr, "join": d.join},
                        }
                    )
        for mname, metric in self.metrics.items():
            for phrase in metric.synonyms_ru + [metric.label_ru, mname]:
                items.append(
                    {
                        "kind": "metric",
                        "name": mname,
                        "phrase": phrase,
                        "payload": {"expr": metric.expr, "label_ru": metric.label_ru},
                    }
                )
        return items


def _parse_fact(name: str, raw: dict[str, Any]) -> Fact:
    return Fact(
        name=name,
        table=raw["table"],
        grain=raw.get("grain", ""),
        time_column=raw.get("time_column", ""),
        require_time_filter=bool(raw.get("require_time_filter", False)),
        dimensions=[
            Dimension(
                name=d["name"],
                expr=d["expr"],
                join=d.get("join"),
                synonyms_ru=d.get("synonyms_ru", []),
            )
            for d in raw.get("dimensions", [])
        ],
        measures=[
            Measure(
                name=m["name"],
                expr=m["expr"],
                synonyms_ru=m.get("synonyms_ru", []),
            )
            for m in raw.get("measures", [])
        ],
        foreign_keys=raw.get("foreign_keys", {}),
    )


def _parse_policies(raw: dict[str, Any]) -> Policies:
    return Policies(
        deny_tables=set(raw.get("deny_tables", [])),
        require_time_filter_tables=set(raw.get("require_time_filter_tables", [])),
        default_limit=int(raw.get("default_limit", 500)),
        max_joins=int(raw.get("max_joins", 5)),
        max_total_cost=float(raw.get("max_total_cost", 1e7)),
        max_plan_rows=int(raw.get("max_plan_rows", 10_000_000)),
        pii_columns_by_role=raw.get("pii_columns_by_role", {}),
    )


def _parse_value_linking(raw: dict[str, Any]) -> list[ValueLinkingColumn]:
    cols_raw = raw.get("value_linking", {}).get("enabled_columns") or []
    out: list[ValueLinkingColumn] = []
    for c in cols_raw:
        alias = c["alias"]
        out.append(
            ValueLinkingColumn(
                alias=alias,
                table=_validate_identifier(c["table"], field=f"value_linking[{alias}].table"),
                column=_validate_identifier(c["column"], field=f"value_linking[{alias}].column"),
                synonyms=c.get("synonyms") or {},
                synonyms_from=c.get("synonyms_from"),
                max_distinct=int(c.get("max_distinct", 2000)),
            )
        )
    return out


def load_semantic(path: Path | None = None) -> SemanticModel:
    src = Path(path or settings.semantic_path)
    raw = yaml.safe_load(src.read_text(encoding="utf-8"))
    return SemanticModel(
        raw=raw,
        entities=raw.get("entities", {}),
        facts={k: _parse_fact(k, v) for k, v in raw.get("facts", {}).items()},
        metrics={
            k: Metric(
                name=k,
                expr=v["expr"],
                label_ru=v.get("label_ru", k),
                synonyms_ru=v.get("synonyms_ru", []),
            )
            for k, v in raw.get("metrics", {}).items()
        },
        policies=_parse_policies(raw.get("policies", {})),
        time_expressions_ru=raw.get("time_expressions", {}).get("ru", {}),
        cities_canonical_ru=raw.get("cities_canonical", {}).get("ru", {}),
        value_linking_columns=_parse_value_linking(raw),
    )


@lru_cache(maxsize=1)
def get_semantic() -> SemanticModel:
    return load_semantic()
