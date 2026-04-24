from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from app.core.garbage import looks_like_garbage


@pytest.mark.parametrize(
    "q",
    [
        "",
        "  ",
        "a",
        "пу",
        "grgsfesgegesg",
        "asdfgh",
        "qwertyui",
        "пуыпупыуыпу",
        "мммм",
        "1234 5678",
        "!!!!???",
        "йцукен йцукен",
        "gkjhgfds gkjhgfds",
    ],
)
def test_garbage_detected(q: str):
    assert looks_like_garbage(q) is True, f"should flag as garbage: {q!r}"


@pytest.mark.parametrize(
    "q",
    [
        "Сколько отмен по городам за прошлую неделю?",
        "средний чек за прошлый месяц",
        "compare cancellation rate by city",
        "выручка в Москве",
        "топ 10 водителей",
        "как изменились поездки неделя к неделе",
    ],
)
def test_real_questions_pass(q: str):
    assert looks_like_garbage(q) is False, f"should NOT flag as garbage: {q!r}"


def test_garbage_module_has_no_heavy_imports():
    backend_root = Path(__file__).resolve().parent.parent
    code = textwrap.dedent(
        """
        import sys
        from app.core.garbage import looks_like_garbage

        heavy = {
            "chromadb",
            "sentence_transformers",
            "sqlglot",
            "fastapi",
            "sqlalchemy",
            "psycopg",
        }
        leaked = heavy & set(sys.modules)
        assert not leaked, f"heavy deps leaked into garbage module: {sorted(leaked)}"

        # Sanity: module still functions in this minimal env.
        assert looks_like_garbage("") is True
        assert looks_like_garbage("Сколько отмен по городам за прошлую неделю?") is False
        print("OK")
        """
    )
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(backend_root),
    )
    assert res.returncode == 0 and "OK" in res.stdout, (
        "garbage module is no longer standalone.\n"
        f"returncode={res.returncode}\n"
        f"stdout={res.stdout!r}\nstderr={res.stderr!r}"
    )
