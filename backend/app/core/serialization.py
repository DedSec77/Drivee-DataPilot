from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any


def serialize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    return value
