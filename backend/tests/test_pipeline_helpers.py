from __future__ import annotations

import pytest

pytest.importorskip("chromadb", reason="pipeline helpers tests need chromadb")

from app.core.pipeline import (
    _extract_column_names,
    _fallback_clarify_options,
    _guess_chart,
)


def test_guess_empty_when_no_rows():
    assert _guess_chart("SELECT 1", ["a"], []) == "empty"


def test_guess_line_for_time_series():
    assert _guess_chart("SELECT wk, n FROM t", ["wk", "n"], [["2026-W01", 1]]) == "line"


def test_guess_pie_for_share_columns():
    sql = "SELECT city, share FROM t WHERE 1=1 LIMIT 5"
    rows = [["A", 0.5], ["B", 0.5]]
    assert _guess_chart(sql, ["city", "share"], rows) == "pie"


def test_guess_pie_when_nl_mentions_top():
    sql = "SELECT city, n FROM t LIMIT 3"
    rows = [["A", 10], ["B", 8], ["C", 6]]
    assert _guess_chart(sql, ["city", "n"], rows, nl_question="Топ-3 города") == "pie"


def test_guess_bar_for_two_columns_few_rows():
    rows = [["A", 1], ["B", 2]]
    assert _guess_chart("SELECT a, b FROM t", ["a", "b"], rows) == "bar"


def test_guess_table_for_three_or_more_columns():
    rows = [[1, 2, 3], [4, 5, 6]]
    assert _guess_chart("SELECT * FROM t", ["a", "b", "c"], rows) == "table"


def test_extract_column_names_filters_short_and_uppercase():
    names = _extract_column_names("SELECT trip_id FROM fct_trips WHERE t > 1")
    assert "trip_id" in names
    assert "fct_trips" in names
    assert "t" not in names
    assert "select" not in names
    assert "FROM".lower() not in names


def test_extract_column_names_lowercases():
    names = _extract_column_names("city_id, City_Name")
    assert "city_id" in names
    assert "city_name" in names


def test_fallback_clarify_options_for_cancellation_keyword():
    out = _fallback_clarify_options("Сколько отмен по городам?")
    assert out is not None
    assert any("отмен" in opt["question"].lower() for opt in out)


def test_fallback_clarify_options_returns_none_for_unknown():
    assert _fallback_clarify_options("совсем непонятный запрос") is None


@pytest.mark.parametrize(
    ("nl", "expected_substr"),
    [
        ("Сравни конверсию по каналам", "доля завершённых"),
        ("Сколько новых клиентов", "пассажиров"),
    ],
)
def test_fallback_clarify_options_routes_by_keyword(nl: str, expected_substr: str):
    out = _fallback_clarify_options(nl)
    assert out is not None
    assert any(expected_substr.lower() in opt["question"].lower() for opt in out)
