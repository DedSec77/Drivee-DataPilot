from __future__ import annotations

from decimal import Decimal

from eval.compare import result_equal as _result_equal


def test_exact_equal():
    assert _result_equal([[1, "Москва"], [2, "СПб"]], [(1, "Москва"), (2, "СПб")])


def test_order_insensitive():
    pred = [[1, "Москва"], [2, "СПб"]]
    gold = [(2, "СПб"), (1, "Москва")]
    assert _result_equal(pred, gold)


def test_float_tolerance_pennies():
    pred = [["Москва", 0.4567], ["СПб", 0.3211]]
    gold = [("Москва", 0.4568), ("СПб", 0.3210)]
    assert _result_equal(pred, gold)


def test_column_order_swap():
    pred = [["Москва", 145], ["СПб", 98]]
    gold = [(145, "Москва"), (98, "СПб")]
    assert _result_equal(pred, gold)


def test_decimal_to_float_coercion():
    pred = [["Москва", 145.0]]
    gold = [("Москва", Decimal("145.00"))]
    assert _result_equal(pred, gold)


def test_null_handling():
    pred = [["Москва", None], ["СПб", 12.5]]
    gold = [("Москва", None), ("СПб", 12.5)]
    assert _result_equal(pred, gold)


def test_different_row_counts_fail():
    assert not _result_equal(
        [["Москва", 1], ["СПб", 2]],
        [("Москва", 1)],
    )


def test_different_values_fail():
    assert not _result_equal(
        [["Москва", 1.0]],
        [("Москва", 2.0)],
    )


def test_empty_both_equal():
    assert _result_equal([], [])


def test_empty_pred_with_gold_fails():
    assert not _result_equal([], [(1, "Москва")])


def test_none_pred_fails():
    assert not _result_equal(None, [(1, "Москва")])
