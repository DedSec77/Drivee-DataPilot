from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _disable_rate_limit():
    try:
        from app.core.rate_limit import limiter
    except Exception:
        yield
        return
    prev = limiter.enabled
    limiter.enabled = False
    try:
        yield
    finally:
        limiter.enabled = prev
