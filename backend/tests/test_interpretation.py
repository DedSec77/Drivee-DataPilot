from __future__ import annotations

from datetime import date

from app.core.interpretation import (
    _resolve_period,
    _tables_used,
    build_interpretation,
)
from app.core.semantic import get_semantic

REF_DATE = date(2026, 4, 22)


def test_resolve_previous_week_concrete_dates():
    p = _resolve_period("previous_week", "", today=REF_DATE)
    assert p is not None
    assert p["start"] == "2026-04-13"
    assert p["end"] == "2026-04-19"
    assert "Пн 2026-04-13" in p["label"]
    assert "Вс 2026-04-19" in p["label"]


def test_resolve_last_7_days_rolling():
    p = _resolve_period("last_7_days", "", today=REF_DATE)
    assert p is not None
    assert p["start"] == "2026-04-15"
    assert p["end"] == "2026-04-22"
    assert "скользящие" in p["label"]


def test_resolve_previous_month_calendar():
    p = _resolve_period("previous_month", "", today=REF_DATE)
    assert p is not None
    assert p["start"] == "2026-03-01"
    assert p["end"] == "2026-03-31"


def test_resolve_yesterday_is_one_day():
    p = _resolve_period("yesterday", "", today=REF_DATE)
    assert p is not None
    assert p["start"] == p["end"] == "2026-04-21"


def test_resolve_falls_back_to_nl_phrase():
    p = _resolve_period(None, "сколько отмен за прошлую неделю?", today=REF_DATE)
    assert p is not None
    assert p["start"] == "2026-04-13"


def test_resolve_returns_none_when_unknown():
    p = _resolve_period("never", "сколько вообще?", today=REF_DATE)
    assert p is None


def test_tables_used_excludes_cte_aliases():
    sql = """
    WITH active AS (
      SELECT rider_id FROM fct_trips
      WHERE trip_start_ts >= now() - interval '60 days'
    )
    SELECT COUNT(*) FROM active
    """
    tables = _tables_used(sql)
    assert "fct_trips" in tables
    assert "active" not in tables


def test_tables_used_dedup_and_join():
    sql = """
    SELECT c.city_name, COUNT(*) AS n
    FROM fct_trips t
    JOIN dim_cities c ON c.city_id = t.city_id
    WHERE t.trip_start_ts >= now() - interval '7 days'
    GROUP BY c.city_name
    """
    tables = _tables_used(sql)
    assert set(tables) == {"fct_trips", "dim_cities"}


def test_build_interpretation_full_payload():
    sem = get_semantic()
    sql = (
        "SELECT c.city_name, COUNT(*) FILTER (WHERE fct_trips.status = 'cancelled') "
        "AS cancellations_total FROM fct_trips JOIN dim_cities c ON c.city_id = fct_trips.city_id "
        "WHERE fct_trips.trip_start_ts >= now() - interval '7 days' GROUP BY c.city_name"
    )
    explainer = {
        "used_metrics": ["cancellations_total"],
        "used_dimensions": ["city_name"],
        "time_range": "previous_week",
        "explanation_ru": "Считаем отмены по городам за прошлую неделю.",
    }
    interp = build_interpretation(
        nl_question="Сколько отмен по городам за прошлую неделю?",
        sql=sql,
        explainer=explainer,
        semantic=sem,
        today=REF_DATE,
    )
    assert interp["period"]["start"] == "2026-04-13"
    assert "fct_trips" in interp["tables"]
    assert "dim_cities" in interp["tables"]
    assert any(f["name"] == "cancellations_total" for f in interp["formulas"])
    formula = next(f for f in interp["formulas"] if f["name"] == "cancellations_total")
    assert "FILTER" in formula["formula"]
    assert formula["source"] == "fct_trips"
    assert "city_name" in interp["dimensions"]
    assert "Метрика" in interp["summary_ru"]
    assert "Период" in interp["summary_ru"]
    assert "fct_trips" in interp["summary_ru"]


def test_build_interpretation_handles_unknown_metric():
    sem = get_semantic()
    sql = "SELECT 1 FROM fct_trips WHERE trip_start_ts >= now()"
    explainer = {
        "used_metrics": ["nonexistent_thing"],
        "used_dimensions": [],
        "time_range": None,
        "explanation_ru": "",
    }
    interp = build_interpretation(
        nl_question="что-то странное",
        sql=sql,
        explainer=explainer,
        semantic=sem,
        today=REF_DATE,
    )

    assert interp["formulas"] == []
    assert "fct_trips" in interp["tables"]

    assert "nonexistent_thing" in interp["summary_ru"]
