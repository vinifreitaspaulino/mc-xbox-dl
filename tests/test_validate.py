"""Tests for structural Bedrock world validation (packer/validate.py)."""

import struct
from pathlib import Path

from mc_xbox_dl.packer.validate import validate_world_dir


def create_valid_world_tree(world_dir: Path) -> None:
    world_dir.mkdir(parents=True, exist_ok=True)
    (world_dir / "levelname.txt").write_text("Test World", encoding="utf-8")

    # Valid level.dat: 4b version, 4b payload size, 0x0A (TAG_Compound) + data
    payload = b"\x0a\x00\x00" + b"\x00" * 17
    header = struct.pack("<II", 10, len(payload))
    (world_dir / "level.dat").write_bytes(header + payload)

    db_dir = world_dir / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    (db_dir / "CURRENT").write_bytes(b"MANIFEST-000001\n")
    (db_dir / "MANIFEST-000001").write_bytes(b"MANIFEST_DATA")


def test_validate_world_dir_success(tmp_path: Path) -> None:
    world_dir = tmp_path / "valid_world"
    create_valid_world_tree(world_dir)

    is_valid, error_msg = validate_world_dir(world_dir)
    assert is_valid is True
    assert error_msg is None


def test_validate_world_dir_missing_level_dat(tmp_path: Path) -> None:
    world_dir = tmp_path / "no_level_dat"
    create_valid_world_tree(world_dir)
    (world_dir / "level.dat").unlink()

    is_valid, error_msg = validate_world_dir(world_dir)
    assert is_valid is False
    assert "level.dat" in str(error_msg)


def test_validate_world_dir_invalid_nbt_magic(tmp_path: Path) -> None:
    world_dir = tmp_path / "invalid_nbt"
    create_valid_world_tree(world_dir)
    # Replace 0x0A with 0xFF
    header = struct.pack("<II", 10, 10)
    (world_dir / "level.dat").write_bytes(header + b"\xff" * 10)

    is_valid, error_msg = validate_world_dir(world_dir)
    assert is_valid is False
    assert "Invalid NBT" in str(error_msg) or "NBT inválido" in str(error_msg)


def test_validate_world_dir_missing_levelname(tmp_path: Path) -> None:
    world_dir = tmp_path / "no_levelname"
    create_valid_world_tree(world_dir)
    (world_dir / "levelname.txt").unlink()

    is_valid, error_msg = validate_world_dir(world_dir)
    assert is_valid is False
    assert "levelname.txt" in str(error_msg)


def test_validate_world_dir_missing_current(tmp_path: Path) -> None:
    world_dir = tmp_path / "no_current"
    create_valid_world_tree(world_dir)
    (world_dir / "db" / "CURRENT").unlink()

    is_valid, error_msg = validate_world_dir(world_dir)
    assert is_valid is False
    assert "db/CURRENT" in str(error_msg)


def test_validate_world_dir_missing_manifest(tmp_path: Path) -> None:
    world_dir = tmp_path / "no_manifest"
    create_valid_world_tree(world_dir)
    (world_dir / "db" / "MANIFEST-000001").unlink()

    is_valid, error_msg = validate_world_dir(world_dir)
    assert is_valid is False
    assert "MANIFEST" in str(error_msg)
