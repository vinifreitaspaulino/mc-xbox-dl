"""Tests for authentication orchestration (auth/__init__.py)."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import respx

from mc_xbox_dl.auth import ensure_valid_session, login_flow
from mc_xbox_dl.config import (
    MSA_DEVICE_CODE_URL,
    MSA_TOKEN_URL,
    XBL_DEVICE_AUTH_URL,
    XBL_SISU_AUTH_URL,
)
from mc_xbox_dl.http import HttpClient
from mc_xbox_dl.session import MsaTokens, SessionData, XblTokens, load_session, save_session


@respx.mock
def test_login_flow_end_to_end(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("time.sleep", lambda s: None)

    # 1. Device code
    respx.post(MSA_DEVICE_CODE_URL).respond(
        200,
        json={
            "user_code": "TEST1234",
            "device_code": "dev_code_val",
            "verification_uri": "https://www.microsoft.com/link",
            "expires_in": 900,
            "interval": 1,
        },
    )

    # 2. Polling
    respx.post(MSA_TOKEN_URL).respond(
        200,
        json={
            "access_token": "msa_acc_val",
            "refresh_token": "msa_ref_val",
            "expires_in": 3600,
        },
    )

    # 3. Device Token
    respx.post(XBL_DEVICE_AUTH_URL).respond(
        200,
        json={
            "Token": "dev_token_val",
            "NotAfter": "2026-10-16T12:00:00Z",
        },
    )

    # 4. SISU Authorization
    respx.post(XBL_SISU_AUTH_URL).respond(
        200,
        json={
            "AuthorizationToken": {
                "Token": "sisu_xsts_token_val",
                "NotAfter": "2026-10-16T04:00:00Z",
                "DisplayClaims": {
                    "xui": [
                        {
                            "uhs": "uhs_val",
                            "xid": "2814999988887777",
                            "gtg": "MasterChief",
                        }
                    ]
                },
            }
        },
    )

    with HttpClient() as client:
        session = login_flow(client)
        assert session.msa.refresh_token == "msa_ref_val"
        assert session.xbl.user_hash == "uhs_val"
        assert session.xbl.gamertag == "MasterChief"
        assert session.xbl.xuid == "2814999988887777"
        assert session.auth_flow == "sisu_device_code"

    saved = load_session()
    assert saved is not None
    assert saved.xbl.gamertag == "MasterChief"


@respx.mock
def test_ensure_valid_session_not_expiring() -> None:
    # Valid session with distant expiration
    future_time = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()
    session = SessionData(
        schema_version=1,
        created_at="2026-10-15T12:00:00Z",
        client_id="cid",
        auth_flow="sisu_device_code",
        msa=MsaTokens(
            refresh_token="ref_tok",
            access_token="acc_tok",
            access_expires_at=future_time,
        ),
        xbl=XblTokens(
            user_hash="uhs",
            xuid="123",
            xsts_token="xsts_tok",
            gamertag="Player1",
            xsts_expires_at=future_time,
        ),
    )
    save_session(session)

    # Should not perform any HTTP token refresh calls
    with HttpClient() as client:
        valid_session = ensure_valid_session(client)
        assert valid_session.msa.access_token == "acc_tok"
        assert valid_session.xbl.gamertag == "Player1"


@respx.mock
def test_ensure_valid_session_auto_refresh() -> None:
    # Session with token about to expire (1 minute remaining)
    near_time = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
    session = SessionData(
        schema_version=1,
        created_at="2026-10-15T12:00:00Z",
        client_id="cid",
        auth_flow="sisu_device_code",
        msa=MsaTokens(
            refresh_token="old_ref",
            access_token="old_acc",
            access_expires_at=near_time,
        ),
        xbl=XblTokens(
            user_hash="uhs",
            xuid="123",
            xsts_token="old_xsts",
            gamertag="Player1",
            xsts_expires_at=near_time,
        ),
    )
    save_session(session)

    # Mock responses for automatic token refresh
    respx.post(MSA_TOKEN_URL).respond(
        200,
        json={
            "access_token": "renewed_acc",
            "refresh_token": "renewed_ref",
            "expires_in": 3600,
        },
    )
    respx.post(XBL_DEVICE_AUTH_URL).respond(
        200,
        json={
            "Token": "renewed_dev_token",
            "NotAfter": "2026-10-16T12:00:00Z",
        },
    )
    respx.post(XBL_SISU_AUTH_URL).respond(
        200,
        json={
            "AuthorizationToken": {
                "Token": "renewed_sisu_xsts",
                "NotAfter": "2026-10-16T04:00:00Z",
                "DisplayClaims": [{"xui": [{"uhs": "uhs", "xid": "123", "gtg": "Player1"}]}],
            }
        },
    )

    with HttpClient() as client:
        valid_session = ensure_valid_session(client)
        assert valid_session.msa.access_token == "renewed_acc"
        assert valid_session.msa.refresh_token == "renewed_ref"
        assert valid_session.xbl.xsts_token == "renewed_sisu_xsts"

    saved = load_session()
    assert saved is not None
    assert saved.msa.access_token == "renewed_acc"
