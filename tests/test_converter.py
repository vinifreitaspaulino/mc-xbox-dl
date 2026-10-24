"""Unit and integration tests for Bedrock to Java conversion (converter.py & CLI)."""

import struct
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import respx

from mc_xbox_dl.cli import main
from mc_xbox_dl.config import CHUNKER_LATEST_RELEASE_URL, SCID, TITLE_STORAGE_BASE_URL
from mc_xbox_dl.errors import ConversionError
from mc_xbox_dl.http import HttpClient
from mc_xbox_dl.packer.converter import (
    check_java_runtime,
    convert_bedrock_to_java,
    ensure_chunker_jar,
    get_java_saves_dir,
    normalize_chunker_format,
    validate_java_world_dir,
)
from mc_xbox_dl.session import MsaTokens, SessionData, XblTokens, save_session


def test_check_java_runtime_valid_openjdk_21(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="",
            stderr=(
                'openjdk version "21.0.2" 2024-01-16\nOpenJDK Runtime Environment (build 21.0.2+13)'
            ),
        )

    monkeypatch.setattr("subprocess.run", fake_run)
    assert check_java_runtime() == 21


def test_check_java_runtime_valid_java_17(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="openjdk 17.0.10 2024-01-16",
            stderr="",
        )

    monkeypatch.setattr("subprocess.run", fake_run)
    assert check_java_runtime() == 17


def test_check_java_runtime_too_low_java_8(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="",
            stderr='java version "1.8.0_392"\nJava(TM) SE Runtime Environment',
        )

    monkeypatch.setattr("subprocess.run", fake_run)
    with pytest.raises(ConversionError) as exc_info:
        check_java_runtime()
    assert exc_info.value.exit_code == 9
    assert "17" in str(exc_info.value)


def test_check_java_runtime_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("java not found")

    monkeypatch.setattr("subprocess.run", fake_run)
    with pytest.raises(ConversionError) as exc_info:
        check_java_runtime()
    assert exc_info.value.exit_code == 9


def test_normalize_chunker_format() -> None:
    assert normalize_chunker_format("1.21.4") == "JAVA_1_21_4"
    assert normalize_chunker_format("1.20") == "JAVA_1_20"
    assert normalize_chunker_format("JAVA_1_20_1") == "JAVA_1_20_1"
    assert normalize_chunker_format("java_1_21_4") == "JAVA_1_21_4"
    assert normalize_chunker_format("v1.20.6") == "JAVA_1_20_6"

    with pytest.raises(ConversionError):
        normalize_chunker_format("")

    with pytest.raises(ConversionError):
        normalize_chunker_format("invalid_version")


@respx.mock
def test_ensure_chunker_jar_downloads_and_caches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jar_target = tmp_path / "bin" / "chunker-cli.jar"
    monkeypatch.setenv("MC_XBOX_DL_CHUNKER_JAR", str(jar_target))

    asset_redirect_url = (
        "https://github.com/HiveGamesOSS/Chunker/releases/download/1.14.0/chunker-cli-1.14.0.jar"
    )
    cdn_url = "https://objects.githubusercontent.com/github-production-release-asset/chunker.jar"
    fake_jar_bytes = b"PK\x03\x04FAKE_CHUNKER_JAR_CONTENT"

    release_route = respx.get(CHUNKER_LATEST_RELEASE_URL).respond(
        200,
        json={
            "tag_name": "1.14.0",
            "assets": [
                {
                    "name": "Chunker-Windows-x64-1.14.0.exe",
                    "browser_download_url": "https://github.com/HiveGamesOSS/Chunker/releases/download/1.14.0/Chunker.exe",
                },
                {
                    "name": "chunker-cli-1.14.0.jar",
                    "browser_download_url": asset_redirect_url,
                },
            ],
        },
    )
    respx.get(asset_redirect_url).respond(302, headers={"Location": cdn_url})
    dl_route = respx.get(cdn_url).respond(
        200,
        content=fake_jar_bytes,
        headers={"Content-Length": str(len(fake_jar_bytes))},
    )

    with HttpClient() as client:
        resolved = ensure_chunker_jar(client, show_progress=False)
        assert resolved == jar_target
        assert jar_target.is_file()
        assert jar_target.read_bytes() == fake_jar_bytes
        assert release_route.call_count == 1
        assert dl_route.call_count == 1

        # Second call should return cached JAR without making any network requests
        resolved_cached = ensure_chunker_jar(client, show_progress=False)
        assert resolved_cached == jar_target
        assert release_route.call_count == 1
        assert dl_route.call_count == 1


def test_convert_bedrock_to_java_execution_and_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bedrock_dir = tmp_path / "bedrock_in"
    bedrock_dir.mkdir()
    (bedrock_dir / "level.dat").write_bytes(b"BEDROCK")

    jar_path = tmp_path / "chunker-cli.jar"
    jar_path.write_bytes(b"PK\x03\x04JAR")

    recorded_cmds: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if cmd[:2] == ["java", "-version"]:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout="",
                stderr='openjdk version "21.0.2"',
            )
        recorded_cmds.append(cmd)
        # Locate the staging output folder passed after "-o"
        out_idx = cmd.index("-o") + 1
        staging_dir = Path(cmd[out_idx])
        staging_dir.mkdir(parents=True, exist_ok=True)
        # Write valid Java gzip level.dat (starts with 0x1F 0x8B) and region/ folder
        (staging_dir / "level.dat").write_bytes(b"\x1f\x8b\x08\x00JAVA_NBT_DATA")
        (staging_dir / "region").mkdir(parents=True, exist_ok=True)
        (staging_dir / "region" / "r.0.0.mca").write_bytes(b"MCA_REGION")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Done", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    target_java_dir = tmp_path / "saves" / "My World"
    out_1 = convert_bedrock_to_java(
        bedrock_world_dir=bedrock_dir,
        output_java_dir=target_java_dir,
        target_format="1.21.4",
        chunker_jar=jar_path,
        memory_limit="4G",
        force=False,
    )
    assert out_1 == target_java_dir
    assert (out_1 / "level.dat").read_bytes().startswith(b"\x1f\x8b")
    assert (out_1 / "region" / "r.0.0.mca").is_file()
    assert "-Xmx4G" in recorded_cmds[0]
    assert "JAVA_1_21_4" in recorded_cmds[0]

    # Second conversion without force should create "My World (2)"
    out_2 = convert_bedrock_to_java(
        bedrock_world_dir=bedrock_dir,
        output_java_dir=target_java_dir,
        target_format="1.21.4",
        chunker_jar=jar_path,
        force=False,
    )
    assert out_2 == tmp_path / "saves" / "My World (2)"
    assert (out_2 / "level.dat").is_file()


def test_validate_java_world_dir_invalid(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty_java"
    empty_dir.mkdir()
    valid, err = validate_java_world_dir(empty_dir)
    assert not valid
    assert err is not None

    # Non-gzip level.dat
    (empty_dir / "level.dat").write_bytes(b"NOT_GZIP")
    valid2, err2 = validate_java_world_dir(empty_dir)
    assert not valid2
    assert "0x1F 0x8B" in (err2 or "")


def test_get_java_saves_dir_windows_and_linux(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MC_JAVA_SAVES_DIR", raising=False)

    # 1. Windows (%APPDATA%\.minecraft\saves)
    monkeypatch.setattr("platform.system", lambda: "Windows")
    appdata = tmp_path / "AppData" / "Roaming"
    (appdata / ".minecraft").mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))

    win_saves = get_java_saves_dir()
    assert win_saves == appdata / ".minecraft" / "saves"
    assert win_saves.is_dir()

    # 2. Linux standard (~/.minecraft/saves)
    monkeypatch.setattr("platform.system", lambda: "Linux")
    fake_home = tmp_path / "linux_home"
    (fake_home / ".minecraft").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    linux_saves = get_java_saves_dir()
    assert linux_saves == fake_home / ".minecraft" / "saves"
    assert linux_saves.is_dir()

    # 3. Linux Flatpak (~/.var/app/com.mojang.Minecraft/data/minecraft/saves)
    flatpak_home = tmp_path / "flatpak_home"
    flatpak_mc = flatpak_home / ".var" / "app" / "com.mojang.Minecraft" / "data" / "minecraft"
    flatpak_mc.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: flatpak_home))

    fp_saves = get_java_saves_dir()
    assert fp_saves == flatpak_mc / "saves"
    assert fp_saves.is_dir()

    # 4. Missing .minecraft raises ConversionError
    missing_home = tmp_path / "empty_home"
    missing_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: missing_home))
    with pytest.raises(ConversionError) as exc_info:
        get_java_saves_dir()
    assert exc_info.value.exit_code == 9


def _make_atom_bytes(rel_path: str, payload: bytes) -> bytes:
    path_bytes = rel_path.encode("utf-8")
    header = bytearray(b"\x00\x02\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00")
    header.append(len(path_bytes))
    return bytes(header) + path_bytes + payload


@respx.mock
def test_cli_download_install_java_end_to_end(
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
        msa=MsaTokens(refresh_token="ref_tok", access_token="acc_tok", access_expires_at=near_time),
        xbl=XblTokens(
            user_hash="uhs123",
            xuid="2814000000000000",
            xsts_token="xsts_val",
            gamertag="TestPlayer",
            xsts_expires_at=near_time,
        ),
    )
    save_session(session)

    # Pre-create fake chunker-cli.jar
    fake_jar = tmp_path / "bin" / "chunker-cli.jar"
    fake_jar.parent.mkdir(parents=True, exist_ok=True)
    fake_jar.write_bytes(b"PK\x03\x04FAKE_JAR")
    monkeypatch.setenv("MC_XBOX_DL_CHUNKER_JAR", str(fake_jar))

    # Mock subprocess.run for java -version and Chunker execution
    def fake_subprocess_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if cmd[:2] == ["java", "-version"]:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout="",
                stderr='openjdk version "21.0.2"',
            )
        out_idx = cmd.index("-o") + 1
        staging = Path(cmd[out_idx])
        staging.mkdir(parents=True, exist_ok=True)
        (staging / "level.dat").write_bytes(b"\x1f\x8b\x08\x00JAVA_LEVEL")
        (staging / "region").mkdir(parents=True, exist_ok=True)
        (staging / "region" / "r.0.0.mca").write_bytes(b"REGION_DATA")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Converted", stderr="")

    monkeypatch.setattr("subprocess.run", fake_subprocess_run)

    # Mock Xbox Cloud endpoints
    list_url = (
        f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({session.xbl.xuid})/scids/{SCID}"
    )
    respx.get(list_url).respond(
        200,
        json={
            "blobs": [
                {
                    "fileName": "WORLD_JAVA,savedgame",
                    "displayName": "Java Survival",
                    "size": 40000,
                    "clientFileTime": "2026-10-15T12:00:00Z",
                }
            ]
        },
    )
    respx.get(f"{list_url}/WORLD_JAVA,savedgame").respond(
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

    payload_level = b"\x0a\x00\x00" + b"\x00" * 17
    header_level = struct.pack("<II", 10, len(payload_level))
    respx.get(f"{list_url}/ATOM_1,binary").respond(
        200, content=_make_atom_bytes("level.dat", header_level + payload_level)
    )
    respx.get(f"{list_url}/ATOM_2,binary").respond(
        200, content=_make_atom_bytes("levelname.txt", b"Java Survival")
    )
    respx.get(f"{list_url}/ATOM_3,binary").respond(
        200, content=_make_atom_bytes("db/CURRENT", b"MANIFEST-000001\n")
    )
    respx.get(f"{list_url}/ATOM_4,binary").respond(
        200, content=_make_atom_bytes("db/MANIFEST-000001", b"MANIFEST_CONTENTS")
    )

    java_saves_dir = tmp_path / ".minecraft" / "saves"
    code = main(
        [
            "download",
            "1",
            "--install-java",
            "--java-saves-dir",
            str(java_saves_dir),
            "--java-version",
            "1.21.4",
        ]
    )
    assert code == 0

    installed_world = java_saves_dir / "Java Survival"
    assert installed_world.is_dir()
    assert (installed_world / "level.dat").read_bytes().startswith(b"\x1f\x8b")
    assert (installed_world / "region" / "r.0.0.mca").is_file()

    captured = capsys.readouterr()
    assert "Java Survival" in captured.out


@respx.mock
def test_cli_download_java_standalone_and_batch(
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
        msa=MsaTokens(refresh_token="ref_tok", access_token="acc_tok", access_expires_at=near_time),
        xbl=XblTokens(
            user_hash="uhs123",
            xuid="2814000000000000",
            xsts_token="xsts_val",
            gamertag="TestPlayer",
            xsts_expires_at=near_time,
        ),
    )
    save_session(session)

    fake_jar = tmp_path / "bin" / "chunker-cli.jar"
    fake_jar.parent.mkdir(parents=True, exist_ok=True)
    fake_jar.write_bytes(b"PK\x03\x04FAKE_JAR")
    monkeypatch.setenv("MC_XBOX_DL_CHUNKER_JAR", str(fake_jar))
    monkeypatch.setattr("time.sleep", lambda s: None)

    def fake_subprocess_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if cmd[:2] == ["java", "-version"]:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout="",
                stderr='openjdk version "21.0.2"',
            )
        out_idx = cmd.index("-o") + 1
        staging = Path(cmd[out_idx])
        staging.mkdir(parents=True, exist_ok=True)
        (staging / "level.dat").write_bytes(b"\x1f\x8b\x08\x00JAVA_LEVEL")
        (staging / "region").mkdir(parents=True, exist_ok=True)
        (staging / "region" / "r.0.0.mca").write_bytes(b"REGION_DATA")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Converted", stderr="")

    monkeypatch.setattr("subprocess.run", fake_subprocess_run)

    list_url = (
        f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({session.xbl.xuid})/scids/{SCID}"
    )
    respx.get(list_url).respond(
        200,
        json={
            "blobs": [
                {
                    "fileName": "WORLD_STANDALONE,savedgame",
                    "displayName": "My World",
                    "size": 40000,
                    "clientFileTime": "2026-10-15T12:00:00Z",
                }
            ]
        },
    )
    respx.get(f"{list_url}/WORLD_STANDALONE,savedgame").respond(
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

    payload_level = b"\x0a\x00\x00" + b"\x00" * 17
    header_level = struct.pack("<II", 10, len(payload_level))
    respx.get(f"{list_url}/ATOM_1,binary").respond(
        200, content=_make_atom_bytes("level.dat", header_level + payload_level)
    )
    respx.get(f"{list_url}/ATOM_2,binary").respond(
        200, content=_make_atom_bytes("levelname.txt", b"My World")
    )
    respx.get(f"{list_url}/ATOM_3,binary").respond(
        200, content=_make_atom_bytes("db/CURRENT", b"MANIFEST-000001\n")
    )
    respx.get(f"{list_url}/ATOM_4,binary").respond(
        200, content=_make_atom_bytes("db/MANIFEST-000001", b"MANIFEST_CONTENTS")
    )

    out_dir = tmp_path / "java_out"
    code = main(["download", "1", "--java", "-o", str(out_dir)])
    assert code == 0

    expected_java_folder = out_dir / "My World (Java)"
    assert expected_java_folder.is_dir()
    assert (expected_java_folder / "level.dat").is_file()
    assert not (out_dir / "My World.mcworld").exists()

    # Batch download with --all --java should skip existing "My World (Java)"
    code_batch = main(["download", "--all", "--java", "-o", str(out_dir)])
    assert code_batch == 0
    captured = capsys.readouterr()
    assert "Java Edition" in captured.out
