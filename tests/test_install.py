"""Tests for directory resolution and world installation.

Covers packer/install.py and packer/locator.py.
"""

import os
import time
from pathlib import Path

import pytest

from mc_xbox_dl.errors import PackagingError
from mc_xbox_dl.packer.install import (
    get_minecraft_worlds_dir,
    install_world_dir,
    is_minecraft_running,
)
from mc_xbox_dl.packer.locator import (
    find_minecraft_profiles,
    resolve_minecraft_worlds_dir,
)


def test_get_minecraft_worlds_dir_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custom_dir = tmp_path / "custom_worlds"
    monkeypatch.setenv("MC_WORLDS_DIR", str(custom_dir))

    result = get_minecraft_worlds_dir()
    assert result == custom_dir
    assert custom_dir.is_dir()


def test_get_minecraft_worlds_dir_gdk_primary_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MC_WORLDS_DIR", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    users_root = tmp_path / "roaming" / "Minecraft Bedrock" / "Users"

    # Ignored folders: "Shared" and non-numeric names
    (users_root / "Shared" / "games" / "com.mojang").mkdir(parents=True)
    (users_root / "UnknownUser" / "games" / "com.mojang").mkdir(parents=True)

    # Valid numeric GDK user directory (minecraftWorlds not created yet; should auto-create)
    numeric_user = users_root / "2535412345678901"
    mojang_dir = numeric_user / "games" / "com.mojang"
    mojang_dir.mkdir(parents=True)

    profiles = find_minecraft_profiles()
    assert len(profiles) == 1
    assert profiles[0].profile_type == "gdk"
    assert profiles[0].user_id == "2535412345678901"
    assert profiles[0].path == mojang_dir / "minecraftWorlds"
    assert (mojang_dir / "minecraftWorlds").is_dir()

    result = get_minecraft_worlds_dir()
    assert result == mojang_dir / "minecraftWorlds"


def test_get_minecraft_worlds_dir_uwp_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MC_WORLDS_DIR", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming_empty"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    # Create default UWP structure
    uwp_path = (
        tmp_path
        / "local"
        / "Packages"
        / "Microsoft.MinecraftUWP_8wekyb3d8bbwe"
        / "LocalState"
        / "games"
        / "com.mojang"
    )
    uwp_path.mkdir(parents=True)

    result = get_minecraft_worlds_dir()
    expected = uwp_path / "minecraftWorlds"
    assert result == expected
    assert expected.is_dir()


def test_get_minecraft_worlds_dir_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MC_WORLDS_DIR", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming_empty"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local_empty"))

    with pytest.raises(PackagingError, match="(?i)could not locate|localizar"):
        get_minecraft_worlds_dir()


def test_resolve_multiple_profiles_auto_most_recent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MC_WORLDS_DIR", raising=False)
    roaming = tmp_path / "roaming"
    monkeypatch.setenv("APPDATA", str(roaming))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local_empty"))

    users_root = roaming / "Minecraft Bedrock" / "Users"
    p1 = users_root / "1000000000000001" / "games" / "com.mojang" / "minecraftWorlds"
    p2 = users_root / "2000000000000002" / "games" / "com.mojang" / "minecraftWorlds"
    p1.mkdir(parents=True)
    p2.mkdir(parents=True)

    # Set distinct timestamps: p2 newer than p1
    os.utime(p1, (time.time() - 3600, time.time() - 3600))
    os.utime(p2, (time.time(), time.time()))

    # Non-interactive mode should select the most recent profile (p2)
    resolved = resolve_minecraft_worlds_dir(interactive=False)
    assert resolved == p2


def test_resolve_multiple_profiles_interactive_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MC_WORLDS_DIR", raising=False)
    roaming = tmp_path / "roaming"
    monkeypatch.setenv("APPDATA", str(roaming))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local_empty"))

    users_root = roaming / "Minecraft Bedrock" / "Users"
    p1 = users_root / "1000000000000001" / "games" / "com.mojang" / "minecraftWorlds"
    p2 = users_root / "2000000000000002" / "games" / "com.mojang" / "minecraftWorlds"
    p1.mkdir(parents=True)
    p2.mkdir(parents=True)

    # p2 newer than p1, so sorted list is [p2, p1]
    os.utime(p1, (time.time() - 3600, time.time() - 3600))
    os.utime(p2, (time.time(), time.time()))

    # User selects item 2 (which corresponds to p1)
    monkeypatch.setattr("builtins.input", lambda _: "2")
    resolved = resolve_minecraft_worlds_dir(interactive=True)
    assert resolved == p1


def test_resolve_manual_install_dir(tmp_path: Path) -> None:
    explicit = tmp_path / "my_custom_mc_folder"
    resolved = resolve_minecraft_worlds_dir(install_dir=explicit)
    assert resolved == explicit
    assert explicit.is_dir()


def test_install_world_dir_success(tmp_path: Path) -> None:
    source = tmp_path / "source_world"
    source.mkdir()
    (source / "level.dat").write_bytes(b"DATA")
    (source / "levelname.txt").write_text("Meu Mundo", encoding="utf-8")
    (source / "db").mkdir()
    (source / "db" / "CURRENT").write_text("MANIFEST-000001", encoding="utf-8")

    worlds_dir = tmp_path / "minecraftWorlds"
    installed = install_world_dir(source, worlds_dir, "Meu Mundo")

    assert installed == worlds_dir / "Meu Mundo"
    assert (installed / "level.dat").read_bytes() == b"DATA"
    assert (installed / "levelname.txt").read_text(encoding="utf-8") == "Meu Mundo"
    assert (installed / "db" / "CURRENT").is_file()


def test_install_world_dir_unique_name(tmp_path: Path) -> None:
    source = tmp_path / "source_world"
    source.mkdir()
    (source / "level.dat").write_bytes(b"DATA")

    worlds_dir = tmp_path / "minecraftWorlds"
    # Create first installation
    p1 = install_world_dir(source, worlds_dir, "Meu Mundo")
    assert p1 == worlds_dir / "Meu Mundo"

    # Second installation with force=False should append suffix (2)
    p2 = install_world_dir(source, worlds_dir, "Meu Mundo", force=False)
    assert p2 == worlds_dir / "Meu Mundo (2)"

    # Third installation with force=True should overwrite base directory
    p3 = install_world_dir(source, worlds_dir, "Meu Mundo", force=True)
    assert p3 == worlds_dir / "Meu Mundo"


def test_install_world_dir_with_world_id(tmp_path: Path) -> None:
    source = tmp_path / "source_world"
    source.mkdir()
    (source / "level.dat").write_bytes(b"DATA")

    worlds_dir = tmp_path / "minecraftWorlds"
    # World name is blank, world_id provided
    installed = install_world_dir(
        source, worlds_dir, world_name="", world_id="WORLDKzY4MVpUNUthZ0E9,savedgame"
    )
    assert installed == worlds_dir / "WORLDKzY4MVpUNUthZ0E9"
    assert (installed / "level.dat").is_file()


def test_is_minecraft_running_true(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess
    from unittest.mock import MagicMock

    monkeypatch.setattr("sys.platform", "win32")
    mock_run = MagicMock(return_value=MagicMock(stdout="Minecraft.Windows.exe 1234"))
    monkeypatch.setattr(subprocess, "run", mock_run)

    assert is_minecraft_running() is True


def test_is_minecraft_running_false(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess
    from unittest.mock import MagicMock

    monkeypatch.setattr("sys.platform", "win32")
    mock_run = MagicMock(return_value=MagicMock(stdout="INFO: No tasks are running"))
    monkeypatch.setattr(subprocess, "run", mock_run)

    assert is_minecraft_running() is False


def test_is_minecraft_running_non_win32(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.platform", "darwin")
    assert is_minecraft_running() is False
