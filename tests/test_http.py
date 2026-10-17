"""Tests for http.py (centralized HTTP client, retries, and debug dumps)."""

from pathlib import Path

import httpx
import pytest
import respx

from mc_xbox_dl.errors import AccessDeniedError, NetworkError
from mc_xbox_dl.http import HttpClient


@respx.mock
def test_http_get_success() -> None:
    url = "https://login.live.com/test"
    respx.get(url).respond(200, json={"status": "ok"})

    with HttpClient() as client:
        resp = client.request("GET", url)
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


@respx.mock
def test_http_retry_on_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda s: None)
    url = "https://titlestorage.xboxlive.com/retry"
    route = respx.get(url)
    route.side_effect = [
        httpx.Response(500, text="Internal Server Error"),
        httpx.Response(200, json={"success": True}),
    ]

    with HttpClient(debug=False, max_retries=2) as client:
        resp = client.request("GET", url)
        assert resp.status_code == 200
        assert resp.json() == {"success": True}

    assert route.call_count == 2


def test_http_disallowed_host() -> None:
    unauthorized_url = "https://unauthorized-domain.com/secret"
    with HttpClient() as client:
        with pytest.raises(AccessDeniedError) as exc_info:
            client.request("GET", unauthorized_url)
        assert "unauthorized destination" in str(exc_info.value).lower()


@respx.mock
def test_http_debug_dump_redaction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    debug_dir = tmp_path / "debug"
    monkeypatch.setattr("mc_xbox_dl.http.DEBUG_DIR", debug_dir)

    url = "https://login.live.com/oauth20_token.srf"
    secret_refresh = "M.R3_ABCDEF123456789"
    secret_access = "EwBAA1234567890"

    respx.post(url).respond(
        200,
        json={
            "access_token": secret_access,
            "refresh_token": secret_refresh,
            "user_id": "12345",
        },
    )

    with HttpClient(debug=True) as client:
        resp = client.request(
            "POST",
            url,
            headers={"Authorization": "Bearer sensitive_bearer_token"},
            data={"refresh_token": secret_refresh},
        )
        assert resp.status_code == 200

    dumps = list(debug_dir.glob("*.json"))
    assert len(dumps) == 1

    dump_content = dumps[0].read_text(encoding="utf-8")
    assert secret_access not in dump_content
    assert secret_refresh not in dump_content
    assert "sensitive_bearer_token" not in dump_content
    assert "***" in dump_content


@respx.mock
def test_http_persistent_error_raises_network_error() -> None:
    url = "https://titlestorage.xboxlive.com/timeout"
    respx.get(url).mock(side_effect=httpx.ConnectTimeout("Connect timeout"))

    with HttpClient(debug=False, max_retries=1) as client:
        with pytest.raises(NetworkError) as exc_info:
            client.request("GET", url)
        assert "timed out" in str(exc_info.value).lower()


@respx.mock
def test_http_user_agent_is_neutral() -> None:
    url = "https://titlestorage.xboxlive.com/test"
    route = respx.get(url).respond(200, json={"ok": True})

    with HttpClient() as client:
        client.request("GET", url)

    assert route.called
    sent_ua = route.calls.last.request.headers.get("User-Agent", "")
    assert "mc-xbox-dl" not in sent_ua.lower()
    assert "Mozilla" in sent_ua or "Windows" in sent_ua
