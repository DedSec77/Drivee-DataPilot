from __future__ import annotations

import contextlib

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.rate_limit import _rl_ask, limiter


@pytest.fixture
def _app_with_real_limiter(monkeypatch):
    monkeypatch.setattr(limiter, "enabled", True)
    with contextlib.suppress(Exception):
        limiter.reset()

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.post("/ping", dependencies=[Depends(_rl_ask)])
    def ping() -> dict[str, str]:
        return {"status": "ok"}

    yield TestClient(app)
    with contextlib.suppress(Exception):
        limiter.reset()


def test_rate_limit_enforces_threshold(_app_with_real_limiter):
    client = _app_with_real_limiter
    ok_count = 0
    rate_limited_count = 0

    for _ in range(35):
        r = client.post("/ping")
        if r.status_code == 200:
            ok_count += 1
        elif r.status_code == 429:
            rate_limited_count += 1

    assert ok_count == 30, f"expected 30 successful, got {ok_count}"
    assert rate_limited_count == 5, f"expected 5 rate-limited, got {rate_limited_count}"


def test_disabled_limiter_allows_unlimited(monkeypatch):
    monkeypatch.setattr(limiter, "enabled", False)

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.post("/ping", dependencies=[Depends(_rl_ask)])
    def ping() -> dict[str, str]:
        return {"status": "ok"}

    client = TestClient(app)
    for _ in range(100):
        r = client.post("/ping")
        assert r.status_code == 200
