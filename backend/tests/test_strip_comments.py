from __future__ import annotations

import pytest

from app.core.guardrails import _strip_comments


def test_drops_dash_dash_comment_to_eol():
    assert _strip_comments("SELECT 1 -- comment\nFROM t").strip() == "SELECT 1 \nFROM t"


def test_drops_block_comment():
    sql = "SELECT 1 /* drop something */ FROM t"
    assert "drop something" not in _strip_comments(sql)


def test_string_literal_with_dashes_is_preserved():
    sql = "SELECT name FROM t WHERE name = 'a--b'"
    assert "'a--b'" in _strip_comments(sql)


def test_string_literal_with_block_comment_token_is_preserved():
    sql = "SELECT 1 FROM t WHERE x = '/* not really */'"
    assert "'/* not really */'" in _strip_comments(sql)


def test_double_quoted_identifier_with_dash_dash_is_preserved():
    sql = 'SELECT "weird--name" FROM t'
    assert '"weird--name"' in _strip_comments(sql)


def test_unterminated_dash_dash_runs_to_end_of_input():
    out = _strip_comments("SELECT 1 -- forever")
    assert "forever" not in out
    assert "SELECT 1" in out


def test_unterminated_block_comment_runs_to_end_of_input():
    out = _strip_comments("SELECT 1 /* unterminated")
    assert "unterminated" not in out


@pytest.mark.parametrize(
    "raw",
    [
        "  \n\n",
        "/* leading */ SELECT 1",
        "SELECT 1 -- after",
    ],
)
def test_output_is_stripped(raw: str):
    assert _strip_comments(raw) == _strip_comments(raw).strip()
