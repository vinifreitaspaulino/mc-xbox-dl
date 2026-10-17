"""Tests for the session module (session.py)."""

import json
from pathlib import Path

from mc_xbox_dl.session import (
    MsaTokens,
    SessionData,
    XblTokens,
    delete_session,
    load_session,
    save_session,
)


def test_session_roundtrip(tmp_path: Path) -> None:
    session_file = tmp_path / "test_session.json"

    session = SessionData(
        schema_version=1,
        created_at="2026-10-15T12:00:00Z",
        client_id="custom_client",
        auth_flow="live_device_code",
        msa=MsaTokens(
            refresh_token="my_refresh_token",
            access_token="my_access_token",
            access_expires_at="2026-10-15T13:00:00Z",
        ),
        xbl=XblTokens(
            user_hash="test_uhs",
            xuid="2814123456789012",
            xsts_token="my_xsts_token",
            gamertag="Steve",
            xsts_expires_at="2026-10-15T13:00:00Z",
        ),
    )

    save_session(session, session_file)
    assert session_file.exists()

    loaded = load_session(session_file)
    assert loaded is not None
    assert loaded.schema_version == 1
    assert loaded.client_id == "custom_client"
    assert loaded.msa.refresh_token == "my_refresh_token"
    assert loaded.msa.access_token == "my_access_token"
    assert loaded.xbl.user_hash == "test_uhs"
    assert loaded.xbl.xuid == "2814123456789012"
    assert loaded.xbl.gamertag == "Steve"


def test_session_nonexistent_file(tmp_path: Path) -> None:
    non_existent = tmp_path / "does_not_exist.json"
    assert load_session(non_existent) is None


def test_session_corrupted_json(tmp_path: Path) -> None:
    corrupted_file = tmp_path / "corrupted.json"
    corrupted_file.write_text("{ this is not valid json :", encoding="utf-8")

    # Should not raise exception
    assert load_session(corrupted_file) is None


def test_session_unknown_schema_version(tmp_path: Path) -> None:
    file = tmp_path / "future_session.json"
    data = {
        "schema_version": 999,
        "msa": {"refresh_token": "token"},
        "xbl": {"user_hash": "uhs", "xuid": "1", "xsts_token": "tok"},
    }
    file.write_text(json.dumps(data), encoding="utf-8")

    assert load_session(file) is None


def test_session_delete(tmp_path: Path) -> None:
    session_file = tmp_path / "del_session.json"
    session = SessionData(
        schema_version=1,
        created_at="2026-10-15T12:00:00Z",
        client_id="cid",
        auth_flow="live_device_code",
        msa=MsaTokens(refresh_token="ref"),
        xbl=XblTokens(user_hash="u", xuid="x", xsts_token="xsts"),
    )
    save_session(session, session_file)
    assert session_file.exists()

    deleted = delete_session(session_file)
    assert deleted is True
    assert not session_file.exists()

    deleted_again = delete_session(session_file)
    assert deleted_again is False
