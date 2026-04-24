from __future__ import annotations

import pytest

from app.api.summarize import _clean_label


def test_plain_phrase_passes_through():
    assert _clean_label("Топ-3 по отменам") == "Топ-3 по отменам"


def test_strips_label_prefix_ru():
    assert _clean_label("Подпись: Отмены по городам") == "Отмены по городам"


def test_strips_label_prefix_en():
    assert _clean_label("Label: Conversion") == "Conversion"


def test_extracts_first_non_empty_line():
    raw = "\n\nТоп по выручке\nдополнительный текст"
    assert _clean_label(raw) == "Топ по выручке"


def test_unwraps_json_label():
    assert _clean_label('{"label": "MAU за месяц"}') == "MAU за месяц"


def test_unwraps_alternative_json_keys():
    assert _clean_label('{"title": "Конверсия"}') == "Конверсия"


def test_strips_quotes_and_trailing_punctuation():
    assert _clean_label('"Конверсия по каналам."') == "Конверсия по каналам"
    assert _clean_label("«Топ городов!»") == "Топ городов"


def test_truncates_overlong_text():
    very_long = "Метрика " * 20
    out = _clean_label(very_long)
    assert len(out) <= 50
    assert out.endswith("…")


def test_empty_input_returns_empty():
    assert _clean_label("") == ""
    assert _clean_label("   ") == ""


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("`Топ-3`", "Топ-3"),
        ("Топ-3.", "Топ-3"),
        ("Топ-3?", "Топ-3"),
    ],
)
def test_punctuation_and_backticks_stripped(raw: str, expected: str):
    assert _clean_label(raw) == expected
