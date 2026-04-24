from __future__ import annotations

import pytest

from app.core.guardrails import GuardConfig, GuardError, ast_validate


@pytest.fixture
def cfg() -> GuardConfig:
    return GuardConfig(
        allowed_tables={"fct_trips", "dim_cities", "dim_channels", "dim_users"},
        deny_tables={"users_raw", "payments_raw"},
        forbidden_columns={"phone_masked", "email_hash"},
        require_time_filter_tables={"fct_trips"},
        time_columns_by_table={"fct_trips": "trip_start_ts"},
    )


def test_reject_drop(cfg):
    with pytest.raises(GuardError) as e:
        ast_validate("DROP TABLE fct_trips", cfg)
    assert e.value.code in ("NON_SELECT", "FORBIDDEN_STMT")


def test_reject_delete(cfg):
    with pytest.raises(GuardError) as e:
        ast_validate("DELETE FROM fct_trips WHERE trip_id > 0", cfg)
    assert e.value.code in ("NON_SELECT", "FORBIDDEN_STMT")


def test_reject_unknown_table(cfg):
    with pytest.raises(GuardError) as e:
        ast_validate("SELECT * FROM payments_secret WHERE trip_start_ts > now() - interval '7 days'", cfg)
    assert e.value.code == "UNKNOWN_TABLE"


def test_reject_deny_table(cfg):
    cfg.allowed_tables = {"fct_trips", "users_raw"}
    with pytest.raises(GuardError) as e:
        ast_validate("SELECT * FROM users_raw WHERE trip_start_ts > now()", cfg)
    assert e.value.code == "DENY_TABLE"


def test_reject_pii_column(cfg):
    with pytest.raises(GuardError) as e:
        ast_validate(
            "SELECT phone_masked FROM dim_users",
            cfg,
        )
    assert e.value.code == "PII_COLUMN"


def test_require_time_filter(cfg):
    with pytest.raises(GuardError) as e:
        ast_validate("SELECT COUNT(*) FROM fct_trips", cfg)
    assert e.value.code == "NO_TIME_FILTER"


def test_too_many_joins(cfg):
    cfg.max_joins = 1
    sql = """
        SELECT 1 FROM fct_trips t
        JOIN dim_cities c ON c.city_id=t.city_id
        JOIN dim_channels ch ON ch.channel_id=t.channel_id
        WHERE t.trip_start_ts > now() - interval '7 days'
    """
    with pytest.raises(GuardError) as e:
        ast_validate(sql, cfg)
    assert e.value.code == "TOO_MANY_JOINS"


def test_inject_limit(cfg):
    sql = "SELECT city_id FROM fct_trips WHERE trip_start_ts > now() - interval '1 day'"
    tree, applied = ast_validate(sql, cfg)
    assert "inject_limit" in applied
    assert tree.args.get("limit") is not None


def test_no_limit_for_group_by_aggregate(cfg):
    sql = """
        SELECT c.city_name, COUNT(*) AS n
        FROM fct_trips t JOIN dim_cities c ON c.city_id = t.city_id
        WHERE t.trip_start_ts >= now() - interval '7 days'
        GROUP BY c.city_name
    """
    tree, applied = ast_validate(sql, cfg)
    assert "inject_limit" not in applied
    assert tree.args.get("limit") is None


def test_no_limit_for_aggregate_only_select(cfg):
    sql = "SELECT COUNT(*) FROM fct_trips WHERE trip_start_ts > now() - interval '1 day'"
    tree, applied = ast_validate(sql, cfg)
    assert "inject_limit" not in applied
    assert tree.args.get("limit") is None


def test_no_limit_for_having_query(cfg):
    sql = """
        SELECT rider_id, COUNT(*) AS n
        FROM fct_trips
        WHERE trip_start_ts > now() - interval '60 days'
        GROUP BY rider_id
        HAVING COUNT(*) > 5
    """
    tree, applied = ast_validate(sql, cfg)
    assert "inject_limit" not in applied


def test_limit_kept_for_window_query(cfg):
    sql = """
        SELECT trip_id, actual_fare,
               LAG(actual_fare) OVER (ORDER BY trip_start_ts) AS prev
        FROM fct_trips
        WHERE trip_start_ts > now() - interval '1 day'
    """
    tree, applied = ast_validate(sql, cfg)
    assert "inject_limit" in applied
    assert tree.args.get("limit") is not None


def test_comment_injection_stripped(cfg):
    sql = "SELECT city_id FROM fct_trips WHERE trip_start_ts > now() -- DROP TABLE"
    tree, _ = ast_validate(sql, cfg)
    out_sql = tree.sql(dialect="postgres").upper()
    assert "DROP" not in out_sql


def test_happy_path(cfg):
    sql = """
      SELECT c.city_name, COUNT(*) AS n
      FROM fct_trips t JOIN dim_cities c ON c.city_id = t.city_id
      WHERE t.trip_start_ts >= now() - interval '7 days'
      GROUP BY c.city_name
    """
    tree, applied = ast_validate(sql, cfg)
    assert "check_allowed_tables" in applied
    assert "check_time_filter" in applied


def test_cte_alias_is_not_unknown_table(cfg):
    sql = """
      WITH by_week AS (
        SELECT date_trunc('week', trip_start_ts) AS wk, COUNT(*) AS n
        FROM fct_trips
        WHERE trip_start_ts >= now() - interval '8 weeks'
        GROUP BY 1
      )
      SELECT wk, n, LAG(n) OVER (ORDER BY wk) AS prev
      FROM by_week ORDER BY wk
    """
    tree, applied = ast_validate(sql, cfg)
    assert "check_allowed_tables" in applied
    assert "check_time_filter" in applied


def test_cities_canonical_substitution(cfg):
    cfg.cities_canonical = {"мск": "Москва", "спб": "Санкт-Петербург"}
    sql = """
      SELECT COUNT(*) FROM fct_trips t JOIN dim_cities c ON c.city_id = t.city_id
      WHERE t.trip_start_ts >= now() - interval '7 days'
        AND c.city_name IN ('мск', 'спб', 'Казань')
    """
    tree, applied = ast_validate(sql, cfg)
    out = tree.sql(dialect="postgres")
    assert "'Москва'" in out
    assert "'Санкт-Петербург'" in out
    assert "'Казань'" in out
    assert any(r.startswith("canon_cities:") for r in applied)


def test_cities_canonical_noop_when_disabled(cfg):
    cfg.cities_canonical = None
    sql = "SELECT 1 FROM fct_trips WHERE trip_start_ts > now() - interval '1 day' AND city_id = 1"
    tree, applied = ast_validate(sql, cfg)
    assert not any(r.startswith("canon_cities") for r in applied)


def test_reject_empty_range_this_week(cfg):
    sql = """
      SELECT c.city_name, COUNT(*) FILTER (WHERE fct_trips.status = 'cancelled') AS n
      FROM fct_trips JOIN dim_cities c ON c.city_id = fct_trips.city_id
      WHERE fct_trips.trip_start_ts >= DATE_TRUNC('WEEK', CURRENT_TIMESTAMP)
        AND fct_trips.trip_start_ts <  DATE_TRUNC('WEEK', CURRENT_TIMESTAMP)
      GROUP BY c.city_name
    """
    with pytest.raises(GuardError) as e:
        ast_validate(sql, cfg)
    assert e.value.code == "EMPTY_RANGE"


def test_reject_empty_range_strict_strict(cfg):
    sql = """
      SELECT 1 FROM fct_trips
      WHERE trip_start_ts > now()
        AND trip_start_ts < now()
    """
    with pytest.raises(GuardError) as e:
        ast_validate(sql, cfg)
    assert e.value.code == "EMPTY_RANGE"


def test_allow_valid_open_window(cfg):
    sql = """
      SELECT 1 FROM fct_trips
      WHERE trip_start_ts >= DATE_TRUNC('WEEK', now())
        AND trip_start_ts <  now()
    """
    tree, applied = ast_validate(sql, cfg)
    assert "check_empty_range" in applied
    assert tree is not None


def test_allow_degenerate_point_interval(cfg):
    sql = """
      SELECT 1 FROM fct_trips
      WHERE trip_start_ts >= DATE_TRUNC('day', now())
        AND trip_start_ts <= DATE_TRUNC('day', now())
    """
    tree, applied = ast_validate(sql, cfg)
    assert "check_empty_range" in applied
    assert tree is not None


def test_nested_cte_chain(cfg):
    sql = """
      WITH first_trip AS (
        SELECT rider_id, MIN(trip_start_ts) AS first_ts FROM fct_trips
        WHERE trip_start_ts >= now() - interval '365 days' GROUP BY rider_id
      ),
      retained AS (
        SELECT f.rider_id FROM first_trip f
        JOIN fct_trips t ON t.rider_id = f.rider_id
        WHERE t.trip_start_ts BETWEEN f.first_ts + interval '30 days'
                                 AND f.first_ts + interval '60 days'
        GROUP BY f.rider_id
      )
      SELECT COUNT(DISTINCT r.rider_id)::float /
             NULLIF(COUNT(DISTINCT f.rider_id), 0) AS d30
      FROM first_trip f LEFT JOIN retained r ON r.rider_id = f.rider_id
    """
    tree, _ = ast_validate(sql, cfg)
    assert tree is not None
