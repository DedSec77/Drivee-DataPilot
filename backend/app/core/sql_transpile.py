from __future__ import annotations

import sqlglot
from loguru import logger


def transpile_sql(sql: str, target_dialect: str) -> str:
    if target_dialect == "postgres":
        return sql
    try:
        transpiled = sqlglot.transpile(sql, read="postgres", write=target_dialect)
        return transpiled[0] if transpiled else sql
    except Exception as e:
        logger.warning(f"[transpile] failed (read=postgres write={target_dialect}): {e}")
        return sql
