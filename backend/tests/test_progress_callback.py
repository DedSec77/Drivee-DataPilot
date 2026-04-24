from __future__ import annotations

import pytest

pytest.importorskip("chromadb", reason="pipeline import requires chromadb")

from app.core.pipeline import _emit


def test_emit_invokes_callback():
    seen: list[tuple[str, str, str | None]] = []

    def cb(stage: str, label: str, detail: str | None) -> None:
        seen.append((stage, label, detail))

    _emit(cb, "retrieving", "ищу", None)
    _emit(cb, "guarding", "проверяю", "1/3")
    assert seen == [
        ("retrieving", "ищу", None),
        ("guarding", "проверяю", "1/3"),
    ]


def test_emit_is_safe_with_null_callback():
    _emit(None, "stage", "label", "detail")


def test_emit_swallows_callback_exceptions():
    def boom(_stage: str, _label: str, _detail: str | None) -> None:
        raise RuntimeError("network died mid-stream")

    _emit(boom, "stage", "label", None)
