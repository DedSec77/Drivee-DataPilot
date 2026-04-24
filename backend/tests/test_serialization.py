from __future__ import annotations

import datetime as dt
from decimal import Decimal

from app.core.serialization import serialize_value


def test_decimal_becomes_float():
    out = serialize_value(Decimal("12.5"))
    assert out == 12.5
    assert isinstance(out, float)


def test_datetime_becomes_iso_string():
    when = dt.datetime(2026, 4, 22, 13, 5, 0)
    assert serialize_value(when) == "2026-04-22T13:05:00"


def test_date_becomes_iso_string():
    when = dt.date(2026, 4, 22)
    assert serialize_value(when) == "2026-04-22"


def test_none_passes_through():
    assert serialize_value(None) is None


def test_native_types_pass_through_unchanged():
    assert serialize_value("Москва") == "Москва"
    assert serialize_value(42) == 42
    assert serialize_value(3.14) == 3.14
    assert serialize_value(True) is True


def test_nested_structures_pass_through():
    payload = [1, 2, 3]
    assert serialize_value(payload) is payload
