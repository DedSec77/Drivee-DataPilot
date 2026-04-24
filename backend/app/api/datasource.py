from __future__ import annotations

import re
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from app.core.auth import require_admin_token, require_api_token
from app.core.config import settings
from app.core.datasource import (
    detect_dialect,
    get_current_dialect,
    get_database_url,
    mask_dsn,
    normalise_dsn,
    set_database_url,
)
from app.core.llm import get_llm
from app.core.rate_limit import rl_admin_write, rl_heavy
from app.core.semantic import get_semantic, load_semantic
from app.db.session import raw_psycopg

router = APIRouter(dependencies=[Depends(require_api_token)])


class DatasourceStatus(BaseModel):
    dsn_masked: str
    connected: bool
    server_version: str | None = None
    current_database: str | None = None
    dialect: str | None = None
    error: str | None = None


@router.get("/datasource/status", response_model=DatasourceStatus)
def datasource_status() -> DatasourceStatus:
    dsn = get_database_url()
    dialect = get_current_dialect()
    try:
        from app.core.datasource import get_engine

        engine = get_engine()
        with engine.connect() as conn:
            probe = (
                "SELECT current_database(), current_setting('server_version')"
                if dialect == "postgres"
                else "SELECT database(), version()"
            )
            row = conn.execute(text(probe)).fetchone()
        return DatasourceStatus(
            dsn_masked=mask_dsn(dsn),
            connected=True,
            current_database=row[0] if row else None,
            server_version=row[1] if row else None,
            dialect=dialect,
        )
    except Exception as e:
        return DatasourceStatus(
            dsn_masked=mask_dsn(dsn),
            connected=False,
            dialect=dialect,
            error=str(e),
        )


class ConnectRequest(BaseModel):
    dsn: str = Field(
        ...,
        max_length=2000,
        description=(
            "DSN подключения. Поддерживаются Postgres и MySQL. Примеры: "
            "`postgresql://user:pass@host:5432/db`, "
            "`mysql://user:pass@host:3306/db`. SQLAlchemy-стиль "
            "(`postgresql+psycopg://...`, `mysql+pymysql://...`) тоже работает."
        ),
    )

    @field_validator("dsn")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("DSN must not be empty")

        v = normalise_dsn(v)
        try:
            detect_dialect(v)
        except ValueError as e:
            raise ValueError(str(e)) from e
        return v


@router.post(
    "/datasource/connect",
    response_model=DatasourceStatus,
    dependencies=[Depends(require_admin_token), rl_heavy],
)
def datasource_connect(req: ConnectRequest) -> DatasourceStatus:
    try:
        info = set_database_url(req.dsn)
    except Exception as e:
        logger.warning(f"[datasource] connect failed: {e}")
        raise HTTPException(status_code=400, detail=f"Не удалось подключиться: {e}") from e

    return DatasourceStatus(
        dsn_masked=mask_dsn(get_database_url()),
        connected=True,
        current_database=info.get("current_database"),
        server_version=info.get("server_version"),
        dialect=info.get("dialect"),
    )


class ColumnInfo(BaseModel):
    name: str
    type: str
    nullable: bool
    is_pk: bool


class FkInfo(BaseModel):
    column: str
    target_table: str
    target_column: str


class TableInfo(BaseModel):
    schema_: str = Field(..., alias="schema")
    name: str
    estimated_rows: int | None = None
    columns: list[ColumnInfo]
    foreign_keys: list[FkInfo]

    model_config = {"populate_by_name": True}


class SchemaInfo(BaseModel):
    database: str | None
    server_version: str | None
    tables: list[TableInfo]


@router.get("/datasource/introspect", response_model=SchemaInfo)
def datasource_introspect(schema: str | None = None) -> SchemaInfo:
    if get_current_dialect() != "postgres":
        raise HTTPException(
            status_code=501,
            detail=(
                "Introspect пока реализован только для Postgres. "
                "Для MySQL используйте раздел «Словарь» — загрузите YAML вручную."
            ),
        )
    try:
        with raw_psycopg() as conn, conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_setting('server_version')")
            meta = cur.fetchone()
            database = meta[0] if meta else None
            server_version = meta[1] if meta else None

            if schema:
                cur.execute(
                    """
                    SELECT n.nspname, c.relname, c.reltuples::bigint
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relkind IN ('r','p')
                      AND n.nspname = %s
                    ORDER BY c.reltuples DESC, c.relname
                    """,
                    (schema,),
                )
            else:
                cur.execute(
                    """
                    SELECT n.nspname, c.relname, c.reltuples::bigint
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relkind IN ('r','p')
                      AND n.nspname NOT LIKE 'pg\\_%' ESCAPE '\\'
                      AND n.nspname <> 'information_schema'
                    ORDER BY c.reltuples DESC, c.relname
                    """
                )
            table_rows = cur.fetchall()
            tables = _build_tables_in_one_pass(cur, table_rows)
        return SchemaInfo(database=database, server_version=server_version, tables=tables)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"introspect failed: {e}") from e


def _build_tables_in_one_pass(cur, table_rows: list[tuple[str, str, int | None]]) -> list[TableInfo]:
    if not table_rows:
        return []

    pairs = [(s, t) for s, t, _ in table_rows]
    cols_by_table = _columns_for_many(cur, pairs)
    fks_by_table = _fks_for_many(cur, pairs)

    return [
        TableInfo(
            schema=schema_name,
            name=table_name,
            estimated_rows=int(est) if est is not None else None,
            columns=cols_by_table.get((schema_name, table_name), []),
            foreign_keys=fks_by_table.get((schema_name, table_name), []),
        )
        for schema_name, table_name, est in table_rows
    ]


def _columns_for_many(cur, pairs: list[tuple[str, str]]) -> dict[tuple[str, str], list[ColumnInfo]]:
    if not pairs:
        return {}
    schemas, tables = zip(*pairs, strict=True)
    cur.execute(
        """
        WITH wanted AS (
            SELECT unnest(%s::text[]) AS s, unnest(%s::text[]) AS t
        )
        SELECT n.nspname, c.relname,
               a.attname,
               format_type(a.atttypid, a.atttypmod),
               NOT a.attnotnull,
               COALESCE(i.indisprimary, false) AS is_pk,
               a.attnum
        FROM wanted w
        JOIN pg_namespace n ON n.nspname = w.s
        JOIN pg_class c ON c.relnamespace = n.oid AND c.relname = w.t
        JOIN pg_attribute a ON a.attrelid = c.oid
        LEFT JOIN pg_index i ON i.indrelid = a.attrelid
                             AND a.attnum = ANY(i.indkey)
                             AND i.indisprimary
        WHERE a.attnum > 0 AND NOT a.attisdropped
        ORDER BY n.nspname, c.relname, a.attnum
        """,
        (list(schemas), list(tables)),
    )
    out: dict[tuple[str, str], list[ColumnInfo]] = {}
    for s, t, name, typ, nullable, is_pk, _attnum in cur.fetchall():
        out.setdefault((s, t), []).append(
            ColumnInfo(name=name, type=typ, nullable=bool(nullable), is_pk=bool(is_pk))
        )
    return out


def _fks_for_many(cur, pairs: list[tuple[str, str]]) -> dict[tuple[str, str], list[FkInfo]]:
    if not pairs:
        return {}
    schemas, tables = zip(*pairs, strict=True)
    cur.execute(
        """
        WITH wanted AS (
            SELECT unnest(%s::text[]) AS s, unnest(%s::text[]) AS t
        )
        SELECT tc.table_schema, tc.table_name,
               kcu.column_name, ccu.table_name, ccu.column_name
        FROM information_schema.table_constraints tc
        JOIN wanted w
             ON tc.table_schema = w.s AND tc.table_name = w.t
        JOIN information_schema.key_column_usage kcu
             ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
             ON ccu.constraint_name = tc.constraint_name
            AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
        """,
        (list(schemas), list(tables)),
    )
    out: dict[tuple[str, str], list[FkInfo]] = {}
    for s, t, col, target_table, target_col in cur.fetchall():
        out.setdefault((s, t), []).append(
            FkInfo(column=col, target_table=target_table, target_column=target_col)
        )
    return out


_DICT_SYSTEM = (
    "Ты помощник, который собирает семантический слой (semantic layer) для NL→SQL "
    "ассистента. На вход — JSON-схема Postgres-БД (таблицы, колонки, FK). "
    "Тебе нужно вернуть YAML-словарь по тому же формату, что использует "
    "Drivee DataPilot.\n\n"
    "ЖЁСТКИЕ ПРАВИЛА:\n"
    "- Верни ТОЛЬКО YAML, без префиксов и пояснений, без обрамления ``` ```.\n"
    "- Все имена метрик/измерений — snake_case латиницей.\n"
    "- Используй только существующие в схеме таблицы и колонки.\n"
    "- На каждую обнаруженную fact-таблицу заведи запись в `facts:`. "
    "Fact-таблица обычно содержит timestamp/date колонку и FK на dim-таблицы.\n"
    "- Для dim-таблиц заведи запись в `entities:` с key и label_column.\n"
    "- Если есть PII-колонки (phone, email, name, passport) — пометь "
    "entity флагом `pii: true` и перечисли поля в `pii_columns`.\n"
    "- Добавь хотя бы 2-3 measures (count, sum, avg) и 2 dimensions для каждого факта.\n"
    "- Заполни `policies` со здравыми дефолтами: default_limit=500, max_joins=5, "
    "max_total_cost=1.0e7, max_plan_rows=10000000, deny_tables=[]. "
    "В `pii_columns_by_role` перечисли raw PII колонки под role `business_user`.\n"
    "- На русские синонимы (synonyms_ru) используй короткие очевидные слова.\n"
    "- Поле `time_expressions.ru` — оставь несколько универсальных выражений "
    "('за последние 7 дней', 'за прошлый месяц' и т.п.) с условиями на time-колонку "
    "первого факта.\n"
    "- Поле `cities_canonical.ru` оставь пустым словарём `{}` если в схеме нет "
    "очевидной таблицы городов.\n"
    "- В корне YAML обязательно: `domain`, `version: 1`, `description`."
)


class GenerateDictResponse(BaseModel):
    yaml_text: str
    raw: str | None = None


@router.post(
    "/datasource/generate-dictionary",
    response_model=GenerateDictResponse,
    dependencies=[Depends(require_admin_token), rl_heavy],
)
def generate_dictionary() -> GenerateDictResponse:
    try:
        schema = datasource_introspect()
    except HTTPException:
        raise
    schema_payload = _summarise_schema(schema)

    llm = get_llm()
    user_msg = "Ниже схема целевой БД в JSON. Сгенерируй YAML-словарь.\n\n" + yaml.safe_dump(
        schema_payload, allow_unicode=True, sort_keys=False
    )
    try:
        raw = llm.primary.complete(_DICT_SYSTEM, user_msg, temperature=0.0)
    except Exception as e:
        logger.warning(f"[datasource] generate-dictionary LLM failed: {e}")
        raise HTTPException(status_code=503, detail=f"LLM недоступен: {e}") from e

    yaml_text = _strip_code_fences(raw).strip()

    try:
        parsed = yaml.safe_load(yaml_text)
        if not isinstance(parsed, dict):
            raise ValueError("ожидался YAML-объект на верхнем уровне")
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"LLM вернул не валидный YAML: {e}",
        ) from e

    return GenerateDictResponse(yaml_text=yaml_text, raw=raw if raw != yaml_text else None)


def _summarise_schema(schema: SchemaInfo) -> dict[str, Any]:
    return {
        "database": schema.database,
        "tables": [
            {
                "name": f"{t.schema_}.{t.name}",
                "estimated_rows": t.estimated_rows,
                "columns": [
                    {
                        "name": c.name,
                        "type": c.type,
                        "nullable": c.nullable,
                        "primary_key": c.is_pk,
                    }
                    for c in t.columns
                ],
                "foreign_keys": [
                    {
                        "column": fk.column,
                        "references": f"{fk.target_table}.{fk.target_column}",
                    }
                    for fk in t.foreign_keys
                ],
            }
            for t in schema.tables
        ],
    }


_FENCE_RE = re.compile(r"^```(?:yaml|yml)?\s*\n(.*?)\n```\s*$", re.DOTALL | re.IGNORECASE)


def _strip_code_fences(text: str) -> str:
    m = _FENCE_RE.match(text.strip())
    return m.group(1) if m else text


class SaveDictRequest(BaseModel):
    yaml_text: str = Field(..., max_length=200_000)


class SaveDictResponse(BaseModel):
    status: str
    path: str
    domain: str | None = None


@router.post(
    "/dictionary/save",
    response_model=SaveDictResponse,
    dependencies=[Depends(require_admin_token), rl_admin_write],
)
def save_dictionary(req: SaveDictRequest) -> SaveDictResponse:
    try:
        parsed = yaml.safe_load(req.yaml_text)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=422, detail=f"YAML parse error: {e}") from e
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=422, detail="YAML root must be a mapping")

    target = settings.semantic_path
    target.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = target.with_suffix(target.suffix + ".tmp")
    tmp_path.write_text(req.yaml_text, encoding="utf-8")
    try:
        load_semantic(tmp_path)
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=422,
            detail=f"YAML загружается, но не валиден как словарь: {e}",
        ) from e
    tmp_path.replace(target)

    get_semantic.cache_clear()
    try:
        from app.core.retrieval import get_retriever

        get_retriever.cache_clear()
    except Exception as e:
        logger.warning(f"[dictionary] retriever cache clear failed: {e}")

    return SaveDictResponse(
        status="ok",
        path=str(target),
        domain=parsed.get("domain"),
    )
