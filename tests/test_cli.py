"""Tests for the command-line interface (cli.py)."""

import struct
from datetime import datetime, timezone
from pathlib import Path

import pytest
import respx

from mc_xbox_dl import __version__
from mc_xbox_dl.cli import main
from mc_xbox_dl.config import SCID, TITLE_STORAGE_BASE_URL
from mc_xbox_dl.session import MsaTokens, SessionData, XblTokens, save_session


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert __version__ in captured.out


def test_cli_no_args_shows_help(capsys: pytest.CaptureFixture[str]) -> None:
    code = main([])
    assert code == 2
    captured = capsys.readouterr()
    assert "mc-xbox-dl" in captured.out


def test_cli_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "mc-xbox-dl" in captured.out
    assert "login" in captured.out
    assert "download" in captured.out


def test_cli_unknown_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["comando_inexistente"])
    assert exc_info.value.code == 2


def test_cli_whoami_not_logged_in(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["whoami"])
    assert code == 3
    captured = capsys.readouterr()
    assert "não está autenticado" in captured.err or "not authenticated" in captured.err.lower()


def test_cli_whoami_logged_in(capsys: pytest.CaptureFixture[str]) -> None:
    session = SessionData(
        schema_version=1,
        created_at="2026-10-15T12:00:00Z",
        client_id="test_client",
        auth_flow="live_device_code",
        msa=MsaTokens(refresh_token="secret_refresh"),
        xbl=XblTokens(
            user_hash="uhs123",
            xuid="2814000000000000",
            xsts_token="xsts_token_value",
            gamertag="TestPlayer",
        ),
    )
    save_session(session)

    code = main(["whoami"])
    assert code == 0
    captured = capsys.readouterr()
    assert "TestPlayer" in captured.out
    assert "2814000000000000" in captured.out


def test_cli_logout(capsys: pytest.CaptureFixture[str]) -> None:
    session = SessionData(
        schema_version=1,
        created_at="2026-10-15T12:00:00Z",
        client_id="test_client",
        auth_flow="live_device_code",
        msa=MsaTokens(refresh_token="secret_refresh"),
        xbl=XblTokens(
            user_hash="uhs123",
            xuid="2814000000000000",
            xsts_token="xsts_token_value",
        ),
    )
    save_session(session)

    code = main(["logout"])
    assert code == 0
    captured = capsys.readouterr()
    assert "encerrada com sucesso" in captured.out or "ended successfully" in captured.out.lower()

    # Second logout should not fail
    code2 = main(["logout"])
    assert code2 == 0
    captured2 = capsys.readouterr()
    assert "Nenhuma sessão ativa" in captured2.out or "no active session" in captured2.out.lower()


def test_cli_download_not_authenticated() -> None:
    code = main(["download", "1"])
    assert code == 3


def test_cli_download_no_target_and_no_all(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["download"])
    assert code == 2
    captured = capsys.readouterr()
    assert "--all" in captured.err


def make_atom_bytes(rel_path: str, payload: bytes) -> bytes:
    path_bytes = rel_path.encode("utf-8")
    header = bytearray(b"\x00\x02\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00")
    header.append(len(path_bytes))
    return bytes(header) + path_bytes + payload


def setup_world_atom_mocks(list_url: str, atom_prefix: str, world_name: str) -> None:
    payload_level = b"\x0a\x00\x00" + b"\x00" * 17
    header_level = struct.pack("<II", 10, len(payload_level))
    atom_level_dat = make_atom_bytes("level.dat", header_level + payload_level)
    atom_level_name = make_atom_bytes("levelname.txt", world_name.encode("utf-8"))
    atom_current = make_atom_bytes("db/CURRENT", b"MANIFEST-000001\n")
    atom_manifest = make_atom_bytes("db/MANIFEST-000001", b"MANIFEST_CONTENTS")

    respx.get(f"{list_url}/{atom_prefix}_1,binary").respond(200, content=atom_level_dat)
    respx.get(f"{list_url}/{atom_prefix}_2,binary").respond(200, content=atom_level_name)
    respx.get(f"{list_url}/{atom_prefix}_3,binary").respond(200, content=atom_current)
    respx.get(f"{list_url}/{atom_prefix}_4,binary").respond(200, content=atom_manifest)


@respx.mock
def test_cli_download_success(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    near_time = datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat()
    session = SessionData(
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
            user_hash="uhs123",
            xuid="2814000000000000",
            xsts_token="xsts_val",
            gamertag="TestPlayer",
            xsts_expires_at=near_time,
        ),
    )
    save_session(session)

    list_url = (
        f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({session.xbl.xuid})/scids/{SCID}"
    )
    respx.get(list_url).respond(
        200,
        json={
            "blobs": [
                {
                    "fileName": "WORLD_TARGET,savedgame",
                    "displayName": "Aventura Fantastica",
                    "size": 50000,
                    "clientFileTime": "2026-10-15T12:00:00Z",
                }
            ]
        },
    )

    manifest_url = f"{list_url}/WORLD_TARGET,savedgame"
    respx.get(manifest_url).respond(
        200,
        json={
            "atoms": {
                "ATOM_LEVEL_DAT": "ATOM_1,binary",
                "ATOM_LEVEL_NAME": "ATOM_2,binary",
                "ATOM_CURRENT": "ATOM_3,binary",
                "ATOM_MANIFEST": "ATOM_4,binary",
            }
        },
    )

    setup_world_atom_mocks(list_url, "ATOM", "Aventura Fantastica")

    out_dir = tmp_path / "saida"
    code = main(["download", "1", "-o", str(out_dir)])
    assert code == 0

    expected_file = out_dir / "Aventura Fantastica.mcworld"
    assert expected_file.is_file()

    captured = capsys.readouterr()
    assert "Mundo salvo com sucesso" in captured.out or "saved successfully" in captured.out.lower()


@respx.mock
def test_cli_download_world_not_found(capsys: pytest.CaptureFixture[str]) -> None:
    near_time = datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat()
    session = SessionData(
        schema_version=1,
        created_at="2026-10-15T12:00:00Z",
        client_id="test_client",
        auth_flow="sisu_device_code",
        msa=MsaTokens(refresh_token="ref_tok", access_expires_at=near_time),
        xbl=XblTokens(
            user_hash="uhs123",
            xuid="2814000000000000",
            xsts_token="xsts_val",
            xsts_expires_at=near_time,
        ),
    )
    save_session(session)

    list_url = (
        f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({session.xbl.xuid})/scids/{SCID}"
    )
    respx.get(list_url).respond(200, json={"blobs": []})

    code = main(["download", "99"])
    assert code == 5


@respx.mock
def test_cli_download_file_exists_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    near_time = datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat()
    session = SessionData(
        schema_version=1,
        created_at="2026-10-15T12:00:00Z",
        client_id="test_client",
        auth_flow="sisu_device_code",
        msa=MsaTokens(refresh_token="ref_tok", access_expires_at=near_time),
        xbl=XblTokens(
            user_hash="uhs123",
            xuid="2814000000000000",
            xsts_token="xsts_val",
            xsts_expires_at=near_time,
        ),
    )
    save_session(session)

    list_url = (
        f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({session.xbl.xuid})/scids/{SCID}"
    )
    respx.get(list_url).respond(
        200,
        json={
            "blobs": [
                {
                    "fileName": "WORLD1,savedgame",
                    "displayName": "Meu Mundo",
                    "size": 1000,
                    "clientFileTime": "2026-10-15T12:00:00Z",
                }
            ]
        },
    )

    # Pre-create existing file
    existing = tmp_path / "Meu Mundo.mcworld"
    existing.write_text("ALREADY_EXISTS")

    code = main(["download", "1", "-o", str(tmp_path)])
    assert code == 2
    captured = capsys.readouterr()
    assert "já existe" in captured.err or "already exists" in captured.err.lower()


@respx.mock
def test_cli_download_all_success(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    near_time = datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat()
    session = SessionData(
        schema_version=1,
        created_at="2026-10-15T12:00:00Z",
        client_id="test_client",
        auth_flow="sisu_device_code",
        msa=MsaTokens(refresh_token="ref_tok", access_expires_at=near_time),
        xbl=XblTokens(
            user_hash="uhs123",
            xuid="2814000000000000",
            xsts_token="xsts_val",
            xsts_expires_at=near_time,
        ),
    )
    save_session(session)

    list_url = (
        f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({session.xbl.xuid})/scids/{SCID}"
    )
    respx.get(list_url).respond(
        200,
        json={
            "blobs": [
                {
                    "fileName": "WORLD_A,savedgame",
                    "displayName": "Mundo A",
                    "size": 1000,
                    "clientFileTime": "2026-10-15T12:00:00Z",
                },
                {
                    "fileName": "WORLD_B,savedgame",
                    "displayName": "Mundo B",
                    "size": 2000,
                    "clientFileTime": "2026-10-14T12:00:00Z",
                },
            ]
        },
    )

    # Manifests
    respx.get(f"{list_url}/WORLD_A,savedgame").respond(
        200,
        json={
            "atoms": {
                "A1": "WA_1,binary",
                "A2": "WA_2,binary",
                "A3": "WA_3,binary",
                "A4": "WA_4,binary",
            }
        },
    )
    respx.get(f"{list_url}/WORLD_B,savedgame").respond(
        200,
        json={
            "atoms": {
                "B1": "WB_1,binary",
                "B2": "WB_2,binary",
                "B3": "WB_3,binary",
                "B4": "WB_4,binary",
            }
        },
    )

    setup_world_atom_mocks(list_url, "WA", "Mundo A")
    setup_world_atom_mocks(list_url, "WB", "Mundo B")

    out_dir = tmp_path / "todos"
    code = main(["download", "--all", "-o", str(out_dir)])
    assert code == 0

    assert (out_dir / "Mundo A.mcworld").is_file()
    assert (out_dir / "Mundo B.mcworld").is_file()

    captured = capsys.readouterr()
    assert "Baixados com sucesso" in captured.out or "Successfully downloaded" in captured.out


@respx.mock
def test_cli_download_all_skips_existing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    near_time = datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat()
    session = SessionData(
        schema_version=1,
        created_at="2026-10-15T12:00:00Z",
        client_id="test_client",
        auth_flow="sisu_device_code",
        msa=MsaTokens(refresh_token="ref_tok", access_expires_at=near_time),
        xbl=XblTokens(
            user_hash="uhs123",
            xuid="2814000000000000",
            xsts_token="xsts_val",
            xsts_expires_at=near_time,
        ),
    )
    save_session(session)

    list_url = (
        f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({session.xbl.xuid})/scids/{SCID}"
    )
    respx.get(list_url).respond(
        200,
        json={
            "blobs": [
                {
                    "fileName": "WORLD_OLD,savedgame",
                    "displayName": "Mundo Antigo",
                    "size": 1000,
                    "clientFileTime": "2026-10-15T12:00:00Z",
                }
            ]
        },
    )

    # Pre-create the file beforehand
    (tmp_path / "Mundo Antigo.mcworld").write_text("ALREADY_EXISTS")

    code = main(["download", "--all", "-o", str(tmp_path)])
    assert code == 0
    captured = capsys.readouterr()
    assert (
        "já existe em disco. Pulando" in captured.out
        or "already exists on disk. Skipping" in captured.out
    )
    assert (tmp_path / "Mundo Antigo.mcworld").read_text() == "ALREADY_EXISTS"


@respx.mock
def test_cli_download_all_continues_on_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    near_time = datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat()
    session = SessionData(
        schema_version=1,
        created_at="2026-10-15T12:00:00Z",
        client_id="test_client",
        auth_flow="sisu_device_code",
        msa=MsaTokens(refresh_token="ref_tok", access_expires_at=near_time),
        xbl=XblTokens(
            user_hash="uhs123",
            xuid="2814000000000000",
            xsts_token="xsts_val",
            xsts_expires_at=near_time,
        ),
    )
    save_session(session)

    list_url = (
        f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({session.xbl.xuid})/scids/{SCID}"
    )
    respx.get(list_url).respond(
        200,
        json={
            "blobs": [
                {
                    "fileName": "WORLD_FAIL,savedgame",
                    "displayName": "Mundo Quebrado",
                    "size": 1000,
                    "clientFileTime": "2026-10-15T12:00:00Z",
                },
                {
                    "fileName": "WORLD_OK,savedgame",
                    "displayName": "Mundo Bom",
                    "size": 2000,
                    "clientFileTime": "2026-10-14T12:00:00Z",
                },
            ]
        },
    )

    # Failing world returns HTTP 500 on manifest request
    respx.get(f"{list_url}/WORLD_FAIL,savedgame").respond(500, text="Server Error")

    # Valid world succeeds normally
    respx.get(f"{list_url}/WORLD_OK,savedgame").respond(
        200,
        json={
            "atoms": {
                "OK1": "WOK_1,binary",
                "OK2": "WOK_2,binary",
                "OK3": "WOK_3,binary",
                "OK4": "WOK_4,binary",
            }
        },
    )
    setup_world_atom_mocks(list_url, "WOK", "Mundo Bom")

    # Should download the valid world even when the broken world fails
    code = main(["download", "--all", "-o", str(tmp_path)])
    assert code == 1  # Exit code 1 indicates partial batch failure

    assert (tmp_path / "Mundo Bom.mcworld").is_file()
    assert not (tmp_path / "Mundo Quebrado.mcworld").exists()

    captured = capsys.readouterr()
    assert "Baixados com sucesso" in captured.out or "Successfully downloaded" in captured.out
    assert "Falhas" in captured.out or "Failed" in captured.out


@respx.mock
def test_cli_download_with_install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("platform.system", lambda: "Windows")
    near_time = datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat()
    session = SessionData(
        schema_version=1,
        created_at="2026-10-15T12:00:00Z",
        client_id="test_client",
        auth_flow="sisu_device_code",
        msa=MsaTokens(refresh_token="ref_tok", access_expires_at=near_time),
        xbl=XblTokens(
            user_hash="uhs123",
            xuid="2814000000000000",
            xsts_token="xsts_val",
            xsts_expires_at=near_time,
        ),
    )
    save_session(session)

    mc_worlds_dir = tmp_path / "installed_worlds"
    monkeypatch.setenv("MC_WORLDS_DIR", str(mc_worlds_dir))

    list_url = (
        f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({session.xbl.xuid})/scids/{SCID}"
    )
    respx.get(list_url).respond(
        200,
        json={
            "blobs": [
                {
                    "fileName": "WORLD_INST,savedgame",
                    "displayName": "Mundo Instalado",
                    "size": 50000,
                    "clientFileTime": "2026-10-15T12:00:00Z",
                }
            ]
        },
    )

    manifest_url = f"{list_url}/WORLD_INST,savedgame"
    respx.get(manifest_url).respond(
        200,
        json={
            "atoms": {
                "A1": "ATOM_1,binary",
                "A2": "ATOM_2,binary",
                "A3": "ATOM_3,binary",
                "A4": "ATOM_4,binary",
            }
        },
    )

    setup_world_atom_mocks(list_url, "ATOM", "Mundo Instalado")

    out_dir = tmp_path / "mcworld_output"
    code = main(["download", "1", "-o", str(out_dir), "--install"])
    assert code == 0

    # Verify that the .mcworld archive was generated
    assert (out_dir / "Mundo Instalado.mcworld").is_file()

    # Verify that the world was installed directly into the game directory
    target_installed = mc_worlds_dir / "Mundo Instalado"
    assert target_installed.is_dir()
    assert (target_installed / "level.dat").is_file()
    assert (target_installed / "levelname.txt").read_text(encoding="utf-8") == "Mundo Instalado"

    captured = capsys.readouterr()
    assert (
        "Mundo instalado diretamente no Minecraft Bedrock" in captured.out
        or "World installed directly into Minecraft Bedrock" in captured.out
    )


@respx.mock
def test_cli_download_with_install_dir_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    near_time = datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat()
    session = SessionData(
        schema_version=1,
        created_at="2026-10-15T12:00:00Z",
        client_id="test_client",
        auth_flow="sisu_device_code",
        msa=MsaTokens(refresh_token="ref_tok", access_expires_at=near_time),
        xbl=XblTokens(
            user_hash="uhs123",
            xuid="2814000000000000",
            xsts_token="xsts_val",
            xsts_expires_at=near_time,
        ),
    )
    save_session(session)

    custom_worlds_dir = tmp_path / "custom_target_worlds"

    list_url = (
        f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({session.xbl.xuid})/scids/{SCID}"
    )
    respx.get(list_url).respond(
        200,
        json={
            "blobs": [
                {
                    "fileName": "WORLD_CUSTOM,savedgame",
                    "displayName": "Mundo Customizado",
                    "size": 50000,
                    "clientFileTime": "2026-10-15T12:00:00Z",
                }
            ]
        },
    )

    manifest_url = f"{list_url}/WORLD_CUSTOM,savedgame"
    respx.get(manifest_url).respond(
        200,
        json={
            "atoms": {
                "A1": "ATOM_1,binary",
                "A2": "ATOM_2,binary",
                "A3": "ATOM_3,binary",
                "A4": "ATOM_4,binary",
            }
        },
    )

    setup_world_atom_mocks(list_url, "ATOM", "Mundo Customizado")

    # Using --install-dir directly (should implicitly activate installation)
    code = main(["download", "1", "--install-dir", str(custom_worlds_dir)])
    assert code == 0

    target_installed = custom_worlds_dir / "Mundo Customizado"
    assert target_installed.is_dir()
    assert (target_installed / "level.dat").is_file()
    assert (target_installed / "levelname.txt").read_text(encoding="utf-8") == "Mundo Customizado"


@respx.mock
def test_cli_download_install_flag_on_linux(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("platform.system", lambda: "Linux")

    near_time = datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat()
    session = SessionData(
        schema_version=1,
        created_at="2026-10-15T12:00:00Z",
        client_id="test_client",
        auth_flow="sisu_device_code",
        msa=MsaTokens(refresh_token="ref_tok", access_expires_at=near_time),
        xbl=XblTokens(
            user_hash="uhs123",
            xuid="2814000000000000",
            xsts_token="xsts_val",
            gamertag="TestPlayer",
            xsts_expires_at=near_time,
        ),
    )
    save_session(session)

    list_url = (
        f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({session.xbl.xuid})/scids/{SCID}"
    )
    respx.get(list_url).respond(
        200,
        json={
            "blobs": [
                {
                    "fileName": "WORLD_LINUX,savedgame",
                    "displayName": "Linux World",
                    "size": 50000,
                    "clientFileTime": "2026-10-15T12:00:00Z",
                }
            ]
        },
    )

    manifest_url = f"{list_url}/WORLD_LINUX,savedgame"
    respx.get(manifest_url).respond(
        200,
        json={
            "atoms": {
                "A1": "ATOM_1,binary",
                "A2": "ATOM_2,binary",
                "A3": "ATOM_3,binary",
                "A4": "ATOM_4,binary",
            }
        },
    )

    setup_world_atom_mocks(list_url, "ATOM", "Linux World")

    # When --install is given on Linux without --install-dir:
    code = main(["download", "1", "--install"])
    assert code == 0

    # .mcworld must be generated in default output folder (tmp_path)
    expected_mcworld = tmp_path / "Linux World.mcworld"
    assert expected_mcworld.is_file()

    # Informative notice with mcpelauncher paths must be printed
    captured = capsys.readouterr()
    assert "mcpelauncher" in captured.out.lower() or "mcpelauncher" in captured.err.lower()
    assert "flatpak" in captured.out.lower() or "flatpak" in captured.err.lower()


def test_cli_login_consent_declined(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "n")
    code = main(["login"])
    assert code == 1
    captured = capsys.readouterr()
    err_lower = captured.err.lower()
    assert (
        "cancelada" in err_lower
        or "cancelled" in err_lower
        or "canceled" in err_lower
        or "declined" in err_lower
    )


def test_cli_login_consent_accepted(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dummy = SessionData(
        schema_version=1,
        created_at="2026-10-15T12:00:00Z",
        client_id="test_client",
        auth_flow="sisu_device_code",
        msa=MsaTokens(refresh_token="ref_tok"),
        xbl=XblTokens(
            user_hash="uhs123",
            xuid="2814000000000000",
            xsts_token="xsts_val",
            gamertag="TestPlayer",
        ),
    )
    monkeypatch.setattr("builtins.input", lambda _: "y")
    monkeypatch.setattr("mc_xbox_dl.cli.login_flow", lambda http: dummy)
    code = main(["login"])
    assert code == 0
    captured = capsys.readouterr()
    assert "TestPlayer" in captured.out


def test_cli_login_with_accept_risk(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dummy = SessionData(
        schema_version=1,
        created_at="2026-10-15T12:00:00Z",
        client_id="test_client",
        auth_flow="sisu_device_code",
        msa=MsaTokens(refresh_token="ref_tok"),
        xbl=XblTokens(
            user_hash="uhs123",
            xuid="2814000000000000",
            xsts_token="xsts_val",
            gamertag="TestPlayer",
        ),
    )

    def should_not_prompt(_: str) -> str:
        pytest.fail(
            "Interactive input prompt should not have been called when --accept-risk is set"
        )

    monkeypatch.setattr("builtins.input", should_not_prompt)
    monkeypatch.setattr("mc_xbox_dl.cli.login_flow", lambda http: dummy)
    code = main(["login", "--accept-risk"])
    assert code == 0
    captured = capsys.readouterr()
    assert "TestPlayer" in captured.out


@respx.mock
def test_cli_list_no_cache_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    near_time = datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat()
    session = SessionData(
        schema_version=1,
        created_at="2026-10-15T12:00:00Z",
        client_id="test_client",
        auth_flow="sisu_device_code",
        msa=MsaTokens(refresh_token="ref_tok", access_expires_at=near_time),
        xbl=XblTokens(
            user_hash="uhs123",
            xuid="2814000000000000",
            xsts_token="xsts_val",
            gamertag="TestPlayer",
            xsts_expires_at=near_time,
        ),
    )
    save_session(session)

    list_url = (
        f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({session.xbl.xuid})/scids/{SCID}"
    )
    route = respx.get(list_url).respond(
        200,
        json={
            "blobs": [
                {
                    "fileName": "WORLD1,savedgame",
                    "displayName": "Direct World",
                    "size": 1000,
                    "clientFileTime": "2026-10-15T12:00:00Z",
                }
            ]
        },
    )

    code = main(["list", "--no-cache"])
    assert code == 0
    assert route.call_count == 1
    captured = capsys.readouterr()
    assert "Direct World" in captured.out


@respx.mock
def test_cli_download_all_fail_fast_on_rate_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("time.sleep", lambda s: None)
    near_time = datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat()
    session = SessionData(
        schema_version=1,
        created_at="2026-10-15T12:00:00Z",
        client_id="test_client",
        auth_flow="sisu_device_code",
        msa=MsaTokens(refresh_token="ref_tok", access_expires_at=near_time),
        xbl=XblTokens(
            user_hash="uhs123",
            xuid="2814000000000000",
            xsts_token="xsts_val",
            gamertag="TestPlayer",
            xsts_expires_at=near_time,
        ),
    )
    save_session(session)

    list_url = (
        f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({session.xbl.xuid})/scids/{SCID}"
    )
    respx.get(list_url).respond(
        200,
        json={
            "blobs": [
                {
                    "fileName": "WORLD_RATE_LIMITED,savedgame",
                    "displayName": "Rate Limited World",
                    "size": 1000,
                    "clientFileTime": "2026-10-15T12:00:00Z",
                },
                {
                    "fileName": "WORLD_NEVER_REACHED,savedgame",
                    "displayName": "Never Reached World",
                    "size": 2000,
                    "clientFileTime": "2026-10-14T12:00:00Z",
                },
            ]
        },
    )

    # World 1 manifest triggers 429 Rate Limit
    respx.get(f"{list_url}/WORLD_RATE_LIMITED,savedgame").respond(429, text="Too Many Requests")
    never_reached_route = respx.get(f"{list_url}/WORLD_NEVER_REACHED,savedgame").respond(
        200, json={"atoms": {}}
    )

    code = main(["download", "--all", "-o", str(tmp_path)])
    assert code == 1
    # World 2 should never have been requested because of fail-fast abort
    assert not never_reached_route.called
    captured = capsys.readouterr()
    assert "429" in captured.err


@respx.mock
def test_cli_download_all_fail_fast_on_access_denied(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    near_time = datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat()
    session = SessionData(
        schema_version=1,
        created_at="2026-10-15T12:00:00Z",
        client_id="test_client",
        auth_flow="sisu_device_code",
        msa=MsaTokens(refresh_token="ref_tok", access_expires_at=near_time),
        xbl=XblTokens(
            user_hash="uhs123",
            xuid="2814000000000000",
            xsts_token="xsts_val",
            gamertag="TestPlayer",
            xsts_expires_at=near_time,
        ),
    )
    save_session(session)

    list_url = (
        f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({session.xbl.xuid})/scids/{SCID}"
    )
    respx.get(list_url).respond(
        200,
        json={
            "blobs": [
                {
                    "fileName": "WORLD_DENIED,savedgame",
                    "displayName": "Denied World",
                    "size": 1000,
                    "clientFileTime": "2026-10-15T12:00:00Z",
                },
                {
                    "fileName": "WORLD_UNREACHED,savedgame",
                    "displayName": "Unreached World",
                    "size": 2000,
                    "clientFileTime": "2026-10-14T12:00:00Z",
                },
            ]
        },
    )

    # World 1 manifest triggers 401 Unauthorized
    respx.get(f"{list_url}/WORLD_DENIED,savedgame").respond(401, text="Unauthorized")
    unreached_route = respx.get(f"{list_url}/WORLD_UNREACHED,savedgame").respond(
        200, json={"atoms": {}}
    )

    code = main(["download", "--all", "-o", str(tmp_path)])
    assert code == 1
    # World 2 should never have been requested because of fail-fast abort
    assert not unreached_route.called
    captured = capsys.readouterr()
    assert (
        "401/403" in captured.err
        or "Autenticação" in captured.err
        or "Authentication" in captured.err
    )
