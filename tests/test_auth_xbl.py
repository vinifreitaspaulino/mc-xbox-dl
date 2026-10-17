"""Tests for auth/xbl.py (Xbox Live and XSTS authentication)."""

import pytest
import respx

from mc_xbox_dl.auth.xbl import authenticate_user_token, authorize_xsts
from mc_xbox_dl.config import XBL_USER_AUTH_URL, XBL_XSTS_AUTH_URL
from mc_xbox_dl.errors import AccessDeniedError, NotAuthenticatedError
from mc_xbox_dl.http import HttpClient


@respx.mock
def test_authenticate_user_token_success() -> None:
    respx.post(XBL_USER_AUTH_URL).respond(
        200,
        json={
            "IssueInstant": "2026-10-15T12:00:00Z",
            "NotAfter": "2026-10-16T12:00:00Z",
            "Token": "mock_xau_token",
            "DisplayClaims": {"xui": [{"uhs": "mock_user_hash_123"}]},
        },
    )

    with HttpClient() as client:
        token_info = authenticate_user_token(client, "mock_msa_access_token")
        assert token_info.token == "mock_xau_token"
        assert token_info.user_hash == "mock_user_hash_123"
        assert token_info.not_after == "2026-10-16T12:00:00Z"


@respx.mock
def test_authenticate_user_token_failure() -> None:
    respx.post(XBL_USER_AUTH_URL).respond(400, text="Bad Request")

    with HttpClient() as client:
        with pytest.raises(NotAuthenticatedError) as exc_info:
            authenticate_user_token(client, "invalid_msa_token")
        assert "Xbox Live" in str(exc_info.value)


@respx.mock
def test_authorize_xsts_success() -> None:
    respx.post(XBL_XSTS_AUTH_URL).respond(
        200,
        json={
            "IssueInstant": "2026-10-15T12:00:00Z",
            "NotAfter": "2026-10-16T04:00:00Z",
            "Token": "mock_xsts_token",
            "DisplayClaims": {
                "xui": [
                    {
                        "uhs": "mock_user_hash_123",
                        "xid": "2814555566667777",
                        "gtg": "HeroPlayer",
                    }
                ]
            },
        },
    )

    with HttpClient() as client:
        xsts = authorize_xsts(client, "mock_user_token")
        assert xsts.token == "mock_xsts_token"
        assert xsts.user_hash == "mock_user_hash_123"
        assert xsts.xuid == "2814555566667777"
        assert xsts.gamertag == "HeroPlayer"
        assert xsts.not_after == "2026-10-16T04:00:00Z"


@respx.mock
def test_authorize_xsts_known_xerr_no_xbox_profile() -> None:
    respx.post(XBL_XSTS_AUTH_URL).respond(
        401,
        json={
            "Identity": "0",
            "XErr": 2148916233,
            "Message": "No Xbox account",
            "Redirect": "https://xbox.com",
        },
    )

    with HttpClient() as client:
        with pytest.raises(AccessDeniedError) as exc_info:
            authorize_xsts(client, "mock_user_token")
        assert "Xbox Live" in str(exc_info.value)
