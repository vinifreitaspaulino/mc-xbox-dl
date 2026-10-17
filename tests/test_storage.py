"""Tests for the storage module (storage/client.py and 'list' command)."""

from datetime import datetime, timezone

import pytest
import respx

from mc_xbox_dl.cli import main
from mc_xbox_dl.config import SCID, TITLE_STORAGE_BASE_URL
from mc_xbox_dl.errors import (
    AccessDeniedError,
    NetworkError,
    RateLimitError,
    WorldNotFoundError,
)
from mc_xbox_dl.http import HttpClient
from mc_xbox_dl.session import MsaTokens, SessionData, XblTokens, save_session
from mc_xbox_dl.storage.client import StorageClient


@pytest.fixture
def dummy_session() -> SessionData:
    near_time = datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat()
    return SessionData(
        schema_version=1,
        created_at="2026-10-15T12:00:00Z",
        client_id="test_client",
        auth_flow="sisu_device_code",
        msa=MsaTokens(
            refresh_token="ref_tok",
            access_token="acc_tok",
            access_expires_at=near_time,
        ),
        xbl=XblTokens(
            user_hash="test_uhs",
            xuid="1000000000000001",
            xsts_token="test_xsts",
            gamertag="TestGamer",
            xsts_expires_at=near_time,
        ),
    )


@respx.mock
def test_storage_list_worlds_connected_storage_success(dummy_session: SessionData) -> None:
    xuid = dummy_session.xbl.xuid
    url = f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({xuid})/scids/{SCID}"
    respx.get(url).respond(
        200,
        json={
            "blobs": [
                {
                    "fileName": "SETTINGS,savedgame",
                    "displayName": "SETTINGS",
                    "size": 1024,
                    "clientFileTime": "2026-10-14T10:00:00Z",
                },
                {
                    "fileName": "WORLD_01,savedgame",
                    "displayName": "Survival World",
                    "size": 1048576,
                    "clientFileTime": "2026-10-14T10:00:00Z",
                },
                {
                    "fileName": "WORLD_02,savedgame",
                    "displayName": "Creative World",
                    "size": 5242880,
                    "clientFileTime": "2026-10-15T15:30:00Z",
                },
            ],
            "pagingInfo": {"totalItems": 3},
        },
    )

    with HttpClient() as http_client:
        client = StorageClient(http_client, dummy_session)
        worlds = client.list_worlds()

    # Only worlds (WORLD_*) should be returned; SETTINGS must be filtered out
    assert len(worlds) == 2
    # Most recent should come first (#1)
    assert worlds[0].name == "Creative World"
    assert worlds[0].index == 1
    assert worlds[0].formatted_size() in ("5,0 MB", "5.0 MB")

    assert worlds[1].name == "Survival World"
    assert worlds[1].index == 2
    assert worlds[1].formatted_size() in ("1,0 MB", "1.0 MB")


@respx.mock
def test_storage_list_worlds_title_storage_fallback(dummy_session: SessionData) -> None:
    xuid = dummy_session.xbl.xuid
    primary_url = f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({xuid})/scids/{SCID}"
    respx.get(primary_url).respond(404)

    # Simulate container endpoint failures
    cs_url = f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({xuid})/scids/{SCID}/containers"
    respx.get(cs_url).respond(404)
    respx.get(f"{cs_url}.json").respond(404)

    # Success in Title Storage fallback
    ts_url = f"{TITLE_STORAGE_BASE_URL}/users/xuid({xuid})/scids/{SCID}/data?maxItems=100"
    respx.get(ts_url).respond(
        200,
        json={
            "documents": [
                {
                    "fileName": "w_test123",
                    "displayName": "Fallback World",
                    "size": 2048,
                    "timestamp": "2026-09-01T12:00:00Z",
                }
            ]
        },
    )

    with HttpClient() as http_client:
        client = StorageClient(http_client, dummy_session)
        worlds = client.list_worlds()

    assert len(worlds) == 1
    assert worlds[0].name == "Fallback World"
    assert worlds[0].world_id == "w_test123"


@respx.mock
def test_storage_list_worlds_access_denied(dummy_session: SessionData) -> None:
    xuid = dummy_session.xbl.xuid
    url = f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({xuid})/scids/{SCID}"
    respx.get(url).respond(401, text="Unauthorized")

    with HttpClient() as http_client:
        client = StorageClient(http_client, dummy_session)
        with pytest.raises(AccessDeniedError):
            client.list_worlds()


@respx.mock
def test_storage_get_world_manifest_and_download_atom(dummy_session: SessionData) -> None:
    xuid = dummy_session.xbl.xuid
    manifest_url = (
        f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({xuid})/"
        f"scids/{SCID}/WORLD_TEST,savedgame"
    )
    respx.get(manifest_url).respond(
        200,
        json={
            "atoms": {
                "EMBEDDED_01": "GUID-01,binary",
                "EMBEDDED_02": "GUID-02,binary",
            }
        },
    )

    atom_url = (
        f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({xuid})/scids/{SCID}/GUID-01,binary"
    )
    respx.get(atom_url).respond(200, content=b"ATOM_BINARY_DATA")

    with HttpClient() as http_client:
        client = StorageClient(http_client, dummy_session)
        manifest = client.get_world_manifest("WORLD_TEST,savedgame")
        assert len(manifest) == 2
        assert manifest["EMBEDDED_01"] == "GUID-01,binary"

        atom_data = client.download_atom("GUID-01,binary")
        assert atom_data == b"ATOM_BINARY_DATA"


@respx.mock
def test_storage_get_world_manifest_not_found(dummy_session: SessionData) -> None:
    xuid = dummy_session.xbl.xuid
    manifest_url = (
        f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({xuid})/"
        f"scids/{SCID}/UNKNOWN,savedgame"
    )
    respx.get(manifest_url).respond(404)

    with HttpClient() as http_client:
        client = StorageClient(http_client, dummy_session)
        with pytest.raises(WorldNotFoundError):
            client.get_world_manifest("UNKNOWN,savedgame")


@respx.mock
def test_storage_download_atom_error(dummy_session: SessionData) -> None:
    xuid = dummy_session.xbl.xuid
    atom_url = (
        f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({xuid})/scids/{SCID}/ERR,binary"
    )
    respx.get(atom_url).respond(500, text="Internal Server Error")

    with HttpClient() as http_client:
        client = StorageClient(http_client, dummy_session)
        with pytest.raises(NetworkError):
            client.download_atom("ERR,binary")


@respx.mock
def test_cli_list_success(
    dummy_session: SessionData,
    capsys: pytest.CaptureFixture[str],
) -> None:
    save_session(dummy_session)

    xuid = dummy_session.xbl.xuid
    url = f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({xuid})/scids/{SCID}"
    respx.get(url).respond(
        200,
        json={
            "blobs": [
                {
                    "fileName": "WORLD1,savedgame",
                    "displayName": "My Minecraft Realm",
                    "size": 10240,
                    "clientFileTime": "2026-10-15T12:00:00Z",
                }
            ]
        },
    )

    code = main(["list"])
    assert code == 0
    captured = capsys.readouterr()
    assert "My Minecraft Realm" in captured.out


@respx.mock
def test_cli_list_empty(
    dummy_session: SessionData,
    capsys: pytest.CaptureFixture[str],
) -> None:
    save_session(dummy_session)

    xuid = dummy_session.xbl.xuid
    url = f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({xuid})/scids/{SCID}"
    respx.get(url).respond(200, json={"blobs": []})

    code = main(["list"])
    assert code == 5
    captured = capsys.readouterr()
    assert "Nenhum mundo encontrado" in captured.err or "No worlds found" in captured.err


def test_cli_list_not_authenticated() -> None:
    code = main(["list"])
    assert code == 3


@respx.mock
def test_storage_caching_behavior(dummy_session: SessionData) -> None:
    xuid = dummy_session.xbl.xuid
    url = f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({xuid})/scids/{SCID}"
    route = respx.get(url).respond(
        200,
        json={
            "blobs": [
                {
                    "fileName": "WORLD_01,savedgame",
                    "displayName": "Cached World",
                    "size": 1048576,
                    "clientFileTime": "2026-10-14T10:00:00Z",
                }
            ]
        },
    )

    with HttpClient() as http_client:
        client = StorageClient(http_client, dummy_session)
        # First call fetches from network and writes cache
        w1 = client.list_worlds(use_cache=True)
        assert len(w1) == 1
        assert route.call_count == 1

        # Second call reads from cache without hitting network
        w2 = client.list_worlds(use_cache=True)
        assert len(w2) == 1
        assert route.call_count == 1

        # Third call with use_cache=False forces network fetch
        w3 = client.list_worlds(use_cache=False)
        assert len(w3) == 1
        assert route.call_count == 2


def test_storage_cache_expiry_and_mismatch(dummy_session: SessionData) -> None:
    with HttpClient() as http_client:
        client = StorageClient(http_client, dummy_session)
        sample_items = [
            {"fileName": "WORLD_01,savedgame", "displayName": "Cached World", "size": 100}
        ]
        client._write_cache(sample_items)

        # Cache should be valid immediately
        assert client._read_cache(ttl=60) == sample_items

        # Expired cache (ttl=0)
        assert client._read_cache(ttl=0) is None

        # Mismatched XUID
        other_session = SessionData(
            schema_version=1,
            created_at=dummy_session.created_at,
            client_id="other_client",
            auth_flow="device_code",
            msa=dummy_session.msa,
            xbl=XblTokens(
                user_hash="other_uhs",
                xuid="9999999999999999",
                xsts_token="other_xsts",
            ),
        )
        other_client = StorageClient(http_client, other_session)
        assert other_client._read_cache(ttl=60) is None


@respx.mock
def test_storage_rate_limiting_raises_ratelimiterror(dummy_session: SessionData) -> None:
    xuid = dummy_session.xbl.xuid
    list_url = f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({xuid})/scids/{SCID}"
    respx.get(list_url).respond(429, text="Rate Limit Exceeded")

    with HttpClient() as http_client:
        client = StorageClient(http_client, dummy_session)
        with pytest.raises(RateLimitError):
            client.list_worlds(use_cache=False)
