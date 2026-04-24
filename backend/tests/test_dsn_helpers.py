from __future__ import annotations

import pytest

from app.core.datasource import mask_dsn, to_psycopg_dsn


@pytest.mark.parametrize(
    ("dsn", "expected"),
    [
        (
            "postgresql+psycopg://drivee:supersecret@host:5432/drivee",
            "postgresql+psycopg://drivee:***@host:5432/drivee",
        ),
        (
            "postgresql://user:p%40ss@127.0.0.1:5432/db",
            "postgresql://user:***@127.0.0.1:5432/db",
        ),
    ],
)
def test_mask_dsn_hides_password(dsn: str, expected: str):
    assert mask_dsn(dsn) == expected


def test_mask_dsn_no_password_is_noop():
    dsn = "postgresql+psycopg://nouser@localhost/db"
    assert mask_dsn(dsn) == dsn


def test_mask_dsn_preserves_query_string():
    dsn = "postgresql+psycopg://u:hunter2@h:5432/d?sslmode=require"
    masked = mask_dsn(dsn)
    assert "sslmode=require" in masked
    assert "hunter2" not in masked
    assert "***" in masked


def test_to_psycopg_dsn_strips_driver_suffix():
    assert to_psycopg_dsn("postgresql+psycopg://u:p@h:5432/d") == "postgresql://u:p@h:5432/d"


def test_to_psycopg_dsn_idempotent_on_plain():
    plain = "postgresql://u:p@h:5432/d"
    assert to_psycopg_dsn(plain) == plain
