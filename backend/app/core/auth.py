from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from app.core.config import settings


def _constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def require_api_token(
    x_api_token: str | None = Header(default=None, alias="X-API-Token"),
) -> None:
    expected = settings.api_token
    if not expected:
        return
    if not x_api_token or not _constant_time_eq(x_api_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-API-Token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_admin_token(
    x_api_token: str | None = Header(default=None, alias="X-API-Token"),
) -> None:
    expected = settings.effective_admin_token
    if not expected:
        return
    if not x_api_token or not _constant_time_eq(x_api_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid admin X-API-Token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def validate_role(role: str | None) -> str:
    candidate = (role or "business_user").strip().lower()
    allowed = settings.allowed_roles_set
    if not allowed:
        return candidate
    if candidate not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown role '{candidate}'. Allowed: {sorted(allowed)}",
        )
    return candidate
