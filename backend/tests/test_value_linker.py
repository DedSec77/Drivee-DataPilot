from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("chromadb")
pytest.importorskip("psycopg")
pytest.importorskip("sqlalchemy")

from app.core.value_linker import (
    ValueLink,
    ValueLinker,
    _AliasEntry,
    _merge,
    _ngrams,
    _normalize,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Москва", "москва"),
        ("Нашёл альтернативу", "нашел альтернативу"),
        ("  trailing  ", "trailing"),
        ("multi   space", "multi space"),
        ("ÉCLAIR", "eclair"),
        ("ё", "е"),
        ("Ё", "е"),
        ("", ""),
    ],
)
def test_normalize(raw: str, expected: str) -> None:
    assert _normalize(raw) == expected


def test_ngrams_basic() -> None:
    out = _ngrams("Москва Санкт-Петербург и Уфа")

    assert "москва" in out
    assert "санкт-петербург" in out
    assert "уфа" in out
    assert "и" not in out

    assert "санкт-петербург уфа" in out
    assert "и москва" not in out


def test_ngrams_dedup() -> None:
    out = _ngrams("Москва Москва Москва")
    assert out.count("москва") == 1


def test_ngrams_max_length() -> None:
    out = _ngrams("a b c d e")
    assert out == []


def test_merge_lower_distance_wins() -> None:
    bag: dict[tuple[str, str], ValueLink] = {}
    embedding = ValueLink(
        token="приложение",
        column="dim_channels.channel_name",
        alias="channel",
        db_value="app",
        distance=0.3,
        method="embedding",
    )
    exact = ValueLink(
        token="app",
        column="dim_channels.channel_name",
        alias="channel",
        db_value="app",
        distance=0.0,
        method="exact",
    )
    _merge(bag, embedding)
    _merge(bag, exact)
    assert bag[("dim_channels.channel_name", "app")].method == "exact"


def test_merge_keeps_separate_columns() -> None:
    bag: dict[tuple[str, str], ValueLink] = {}
    a = ValueLink(
        token="system",
        column="fct_trips.cancellation_party",
        alias="cancel_party",
        db_value="system",
        distance=0.0,
        method="exact",
    )
    b = ValueLink(
        token="system",
        column="other.col",
        alias="other",
        db_value="system",
        distance=0.0,
        method="exact",
    )
    _merge(bag, a)
    _merge(bag, b)
    assert len(bag) == 2


def _stub_linker() -> ValueLinker:
    semantic = MagicMock()
    semantic.value_linking_columns = []
    semantic.cities_canonical_ru = {}
    chroma_client = MagicMock()
    chroma_client.get_or_create_collection.return_value = MagicMock()
    embedder = MagicMock()
    linker = ValueLinker(
        semantic=semantic,
        embedder=embedder,
        chroma_client=chroma_client,
    )

    linker._indexed = True

    linker.col.query.return_value = {
        "distances": [[]],
        "metadatas": [[]],
        "documents": [[]],
    }
    embedder.encode.return_value = MagicMock(tolist=lambda: [[0.0] * 4])
    return linker


def _add_alias(
    linker: ValueLinker,
    surface: str,
    db_value: str,
    column: str = "dim_channels.channel_name",
    alias: str = "channel",
) -> None:
    entry = _AliasEntry(db_value=db_value, column=column, alias=alias)
    linker._exact.setdefault(surface.lower(), []).append(entry)
    linker._unaccent.setdefault(_normalize(surface), []).append(entry)


def test_link_exact_match() -> None:
    linker = _stub_linker()
    _add_alias(linker, "айос", "app")
    out = linker.link("Сколько отмен через айос за неделю?")
    assert any(v.db_value == "app" and v.method == "exact" and v.alias == "channel" for v in out)


def test_link_unaccent_match() -> None:
    linker = _stub_linker()
    _add_alias(
        linker,
        "нашёл альтернативу",
        "нашёл альтернативу",
        column="fct_trips.cancellation_reason",
        alias="cancel_reason",
    )
    out = linker.link("сколько отмен по причине нашел альтернативу?")
    assert any(
        v.alias == "cancel_reason" and v.db_value == "нашёл альтернативу" and v.method == "unaccent"
        for v in out
    )


def test_link_dedupes_across_methods() -> None:
    linker = _stub_linker()
    _add_alias(linker, "приложение", "app")
    _add_alias(linker, "app", "app")
    out = linker.link("сравни заказы через приложение и app")
    app_hits = [v for v in out if v.db_value == "app"]
    assert len(app_hits) == 1, f"expected dedup, got {app_hits}"
    assert app_hits[0].method == "exact"


def test_link_no_match_returns_empty() -> None:
    linker = _stub_linker()
    _add_alias(linker, "айос", "app")
    out = linker.link("What is the weather in Tokyo?")
    assert out == []


def test_link_embedding_fallback_threshold() -> None:
    linker = _stub_linker()

    linker.col.query.return_value = {
        "distances": [[0.9]],
        "metadatas": [
            [
                {
                    "column": "dim_channels.channel_name",
                    "alias": "channel",
                    "db_value": "app",
                    "source": "synonym",
                }
            ]
        ],
        "documents": [["приложение"]],
    }
    out = linker.link("совершенно неуместный вопрос про что-то постороннее")
    assert all(v.method != "embedding" for v in out)


def test_link_embedding_below_threshold_is_kept() -> None:
    linker = _stub_linker()
    linker.col.query.return_value = {
        "distances": [[0.2]],
        "metadatas": [
            [
                {
                    "column": "dim_channels.channel_name",
                    "alias": "channel",
                    "db_value": "app",
                    "source": "synonym",
                }
            ]
        ],
        "documents": [["мобильное приложение"]],
    }
    out = linker.link("закажи в мобильном")
    assert any(v.method == "embedding" and v.db_value == "app" for v in out)


def test_link_max_links_caps_output() -> None:
    linker = _stub_linker()
    for word, val in [
        ("один", "Москва"),
        ("два", "Санкт-Петербург"),
        ("три", "Казань"),
        ("четыре", "Уфа"),
    ]:
        _add_alias(
            linker,
            word,
            val,
            column="dim_cities.city_name",
            alias="city",
        )
    q = "поездки в один два три четыре городах"
    out = linker.link(q, max_links=2)
    assert len(out) == 2


def test_link_orders_by_distance_then_token_length() -> None:
    linker = _stub_linker()
    _add_alias(
        linker,
        "нашёл",
        "нашёл альтернативу",
        column="fct_trips.cancellation_reason",
        alias="cancel_reason",
    )
    _add_alias(
        linker,
        "нашёл альтернативу",
        "нашёл альтернативу",
        column="fct_trips.cancellation_reason",
        alias="cancel_reason",
    )
    out = linker.link("отмены потому что нашёл альтернативу")

    assert out[0].token == "нашёл альтернативу"
