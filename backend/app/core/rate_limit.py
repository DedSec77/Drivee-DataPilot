from __future__ import annotations

from fastapi import Depends, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    enabled=settings.rate_limit_enabled,
    storage_uri=settings.rate_limit_storage_uri,
)


@limiter.limit("30/minute")
def _rl_ask(request: Request) -> None:
    return None


@limiter.limit("20/minute")
def _rl_stream(request: Request) -> None:
    return None


@limiter.limit("60/minute")
def _rl_execute(request: Request) -> None:
    return None


@limiter.limit("60/minute")
def _rl_summarize(request: Request) -> None:
    return None


@limiter.limit("30/minute")
def _rl_admin_read(request: Request) -> None:
    return None


@limiter.limit("10/minute")
def _rl_admin_write(request: Request) -> None:
    return None


@limiter.limit("5/minute")
def _rl_heavy(request: Request) -> None:
    return None


rl_ask = Depends(_rl_ask)
rl_stream = Depends(_rl_stream)
rl_execute = Depends(_rl_execute)
rl_summarize = Depends(_rl_summarize)
rl_admin_read = Depends(_rl_admin_read)
rl_admin_write = Depends(_rl_admin_write)
rl_heavy = Depends(_rl_heavy)
