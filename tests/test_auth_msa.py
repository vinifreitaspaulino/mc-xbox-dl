"""Tests for auth/msa.py (Microsoft Account authentication)."""

import httpx
import pytest
import respx

from mc_xbox_dl.auth.msa import poll_device_code, refresh_msa_token, request_device_code
from mc_xbox_dl.config import MSA_DEVICE_CODE_URL, MSA_TOKEN_URL
from mc_xbox_dl.errors import AccessDeniedError, NotAuthenticatedError
from mc_xbox_dl.http import HttpClient


@respx.mock
def test_request_device_code_success() -> None:
    respx.post(MSA_DEVICE_CODE_URL).respond(
        200,
        json={
            "user_code": "ABCD1234",
            "device_code": "opaque_code_xyz",
            "verification_uri": "https://www.microsoft.com/link",
            "expires_in": 900,
            "interval": 5,
        },
    )

    with HttpClient() as client:
        resp = request_device_code(client)
        assert resp.user_code == "ABCD1234"
        assert resp.device_code == "opaque_code_xyz"
        assert resp.verification_uri == "https://www.microsoft.com/link"
        assert resp.expires_in == 900
        assert resp.interval == 5


@respx.mock
def test_poll_device_code_pending_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    # Avoid real sleep in tests
    monkeypatch.setattr("time.sleep", lambda s: None)

    route = respx.post(MSA_TOKEN_URL)
    route.side_effect = [
        httpx.Response(400, json={"error": "authorization_pending"}),
        httpx.Response(400, json={"error": "authorization_pending"}),
        httpx.Response(
            200,
            json={
                "access_token": "acc_tok_123",
                "refresh_token": "ref_tok_456",
                "expires_in": 3600,
                "user_id": "u123",
            },
        ),
    ]

    with HttpClient() as client:
        resp = poll_device_code(client, device_code="opaque_code_xyz", interval=1)
        assert resp.access_token == "acc_tok_123"
        assert resp.refresh_token == "ref_tok_456"
        assert resp.expires_in == 3600
        assert resp.user_id == "u123"

    assert route.call_count == 3


@respx.mock
def test_poll_device_code_slow_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda s: None)

    route = respx.post(MSA_TOKEN_URL)
    route.side_effect = [
        httpx.Response(400, json={"error": "slow_down"}),
        httpx.Response(
            200,
            json={
                "access_token": "acc_tok_ok",
                "refresh_token": "ref_tok_ok",
                "expires_in": 3600,
            },
        ),
    ]

    with HttpClient() as client:
        resp = poll_device_code(client, device_code="opaque_code_xyz", interval=1)
        assert resp.access_token == "acc_tok_ok"


@respx.mock
def test_poll_device_code_expired() -> None:
    respx.post(MSA_TOKEN_URL).respond(400, json={"error": "expired_token"})

    with HttpClient() as client:
        with pytest.raises(NotAuthenticatedError) as exc_info:
            poll_device_code(client, device_code="opaque_code_xyz", interval=0)
        assert "expired" in str(exc_info.value).lower()


@respx.mock
def test_poll_device_code_access_denied() -> None:
    respx.post(MSA_TOKEN_URL).respond(400, json={"error": "access_denied"})

    with HttpClient() as client:
        with pytest.raises(AccessDeniedError) as exc_info:
            poll_device_code(client, device_code="opaque_code_xyz", interval=0)
        assert "denied" in str(exc_info.value).lower() or "cancelled" in str(exc_info.value).lower()


@respx.mock
def test_refresh_msa_token_success() -> None:
    respx.post(MSA_TOKEN_URL).respond(
        200,
        json={
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "expires_in": 7200,
        },
    )

    with HttpClient() as client:
        resp = refresh_msa_token(client, refresh_token="old_refresh_token")
        assert resp.access_token == "new_access_token"
        assert resp.refresh_token == "new_refresh_token"
        assert resp.expires_in == 7200


@respx.mock
def test_refresh_msa_token_invalid_grant() -> None:
    respx.post(MSA_TOKEN_URL).respond(400, json={"error": "invalid_grant"})

    with HttpClient() as client:
        with pytest.raises(NotAuthenticatedError) as exc_info:
            refresh_msa_token(client, refresh_token="revoked_token")
        assert "revoked" in str(exc_info.value).lower() or "expired" in str(exc_info.value).lower()
