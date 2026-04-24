from __future__ import annotations

import pytest
from psycopg import sql

from app.core.semantic import _parse_value_linking, _validate_identifier


def test_identifier_accepts_snake_case():
    assert _validate_identifier("fct_trips", field="table") == "fct_trips"
    assert _validate_identifier("city_id", field="column") == "city_id"
    assert _validate_identifier("_private", field="column") == "_private"
    assert _validate_identifier("col_123", field="column") == "col_123"


@pytest.mark.parametrize(
    "bad",
    [
        "'; DROP TABLE users; --",
        "fct_trips; DELETE FROM users",
        "*",
        "a b",
        "1col",
        "",
        "fct-trips",
        'col"; SELECT * FROM users; --',
        "col.subcol",
    ],
)
def test_identifier_rejects_injections(bad):
    with pytest.raises(ValueError, match="Недопустимый SQL-идентификатор"):
        _validate_identifier(bad, field="test")


def test_parse_value_linking_rejects_malicious_yaml():
    bad_yaml = {
        "value_linking": {
            "enabled_columns": [
                {
                    "alias": "cities",
                    "table": "dim_cities; DROP TABLE fct_trips; --",
                    "column": "city_name",
                }
            ]
        }
    }
    with pytest.raises(ValueError, match="value_linking\\[cities\\]\\.table"):
        _parse_value_linking(bad_yaml)


def test_parse_value_linking_rejects_malicious_column():
    bad_yaml = {
        "value_linking": {
            "enabled_columns": [
                {
                    "alias": "channels",
                    "table": "dim_channels",
                    "column": "name; TRUNCATE users",
                }
            ]
        }
    }
    with pytest.raises(ValueError, match="value_linking\\[channels\\]\\.column"):
        _parse_value_linking(bad_yaml)


def test_parse_value_linking_accepts_valid():
    good_yaml = {
        "value_linking": {
            "enabled_columns": [
                {
                    "alias": "cities",
                    "table": "dim_cities",
                    "column": "city_name",
                    "synonyms": {},
                }
            ]
        }
    }
    cols = _parse_value_linking(good_yaml)
    assert len(cols) == 1
    assert cols[0].table == "dim_cities"
    assert cols[0].column == "city_name"


def test_psycopg_identifier_quotes_bad_input_safely():
    rendered = (
        sql.SQL("SELECT {col} FROM {tbl}")
        .format(
            col=sql.Identifier('col"; DROP TABLE x; --'),
            tbl=sql.Identifier("t"),
        )
        .as_string(None)
    )

    assert "DROP" in rendered
    assert rendered.startswith('SELECT "')
    assert '""' in rendered
