from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core import auth
from app.core.config import settings


def test_validate_role_accepts_known_role(monkeypatch):
    monkeypatch.setattr(settings, "allowed_roles", "business_user,analyst")
    assert auth.validate_role("analyst") == "analyst"
    assert auth.validate_role("business_user") == "business_user"


def test_validate_role_normalises_case_and_whitespace(monkeypatch):
    monkeypatch.setattr(settings, "allowed_roles", "business_user,analyst")
    assert auth.validate_role(" Analyst ") == "analyst"


def test_validate_role_rejects_unknown_role(monkeypatch):
    monkeypatch.setattr(settings, "allowed_roles", "business_user,analyst")
    with pytest.raises(HTTPException) as exc:
        auth.validate_role("admin")
    assert exc.value.status_code == 400


def test_validate_role_defaults_to_business_user(monkeypatch):
    monkeypatch.setattr(settings, "allowed_roles", "business_user,analyst")
    assert auth.validate_role(None) == "business_user"
    assert auth.validate_role("") == "business_user"


def test_require_api_token_no_op_when_unset(monkeypatch):
    monkeypatch.setattr(settings, "api_token", "")
    auth.require_api_token(x_api_token=None)
    auth.require_api_token(x_api_token="anything")


def test_require_api_token_rejects_missing_header(monkeypatch):
    monkeypatch.setattr(settings, "api_token", "secret")
    with pytest.raises(HTTPException) as exc:
        auth.require_api_token(x_api_token=None)
    assert exc.value.status_code == 401


def test_require_api_token_rejects_wrong_token(monkeypatch):
    monkeypatch.setattr(settings, "api_token", "secret")
    with pytest.raises(HTTPException) as exc:
        auth.require_api_token(x_api_token="not-the-secret")
    assert exc.value.status_code == 401


def test_require_api_token_accepts_correct_token(monkeypatch):
    monkeypatch.setattr(settings, "api_token", "secret")
    auth.require_api_token(x_api_token="secret")


def test_require_admin_token_falls_back_to_api_token(monkeypatch):
    monkeypatch.setattr(settings, "api_token", "shared")
    monkeypatch.setattr(settings, "admin_token", "")
    auth.require_admin_token(x_api_token="shared")
    with pytest.raises(HTTPException):
        auth.require_admin_token(x_api_token="wrong")


def test_require_admin_token_uses_dedicated_token_when_set(monkeypatch):
    monkeypatch.setattr(settings, "api_token", "shared")
    monkeypatch.setattr(settings, "admin_token", "stronger")
    auth.require_admin_token(x_api_token="stronger")
    with pytest.raises(HTTPException):
        auth.require_admin_token(x_api_token="shared")
