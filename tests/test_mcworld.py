"""Tests for .mcworld packaging and filename sanitization (packer/mcworld.py)."""

import zipfile
from pathlib import Path

import pytest

from mc_xbox_dl.packer.mcworld import (
    create_mcworld,
    resolve_unique_filepath,
    sanitize_filename,
)


def test_sanitize_filename_special_chars() -> None:
    assert sanitize_filename('Mundo: do "Herobrine" <teste>?*') == "Mundo do Herobrine teste"
    assert sanitize_filename("   ...Espaços e Pontos...   ") == "Espaços e Pontos"
    assert sanitize_filename("") == "World"
    assert sanitize_filename("???") == "World"


def test_sanitize_filename_reserved_windows_names() -> None:
    assert sanitize_filename("CON") == "CON_world"
    assert sanitize_filename("aux.txt") == "aux.txt_world"
    assert sanitize_filename("NUL") == "NUL_world"


def test_resolve_unique_filepath(tmp_path: Path) -> None:
    # 1. Does not exist yet
    p1 = resolve_unique_filepath(tmp_path, "Meu Mundo")
    assert p1 == tmp_path / "Meu Mundo.mcworld"
    p1.touch()

    # 2. Already exists, should generate suffix (2)
    p2 = resolve_unique_filepath(tmp_path, "Meu Mundo")
    assert p2 == tmp_path / "Meu Mundo (2).mcworld"
    p2.touch()

    # 3. (2) already exists, should generate suffix (3)
    p3 = resolve_unique_filepath(tmp_path, "Meu Mundo")
    assert p3 == tmp_path / "Meu Mundo (3).mcworld"


def test_create_mcworld_zip_structure(tmp_path: Path) -> None:
    world_dir = tmp_path / "source_world"
    world_dir.mkdir()
    (world_dir / "level.dat").write_bytes(b"LEVEL_DAT_BYTES")
    (world_dir / "levelname.txt").write_text("Hello World", encoding="utf-8")
    db_dir = world_dir / "db"
    db_dir.mkdir()
    (db_dir / "CURRENT").write_bytes(b"MANIFEST-000001\n")

    output_mcworld = tmp_path / "output.mcworld"
    result_path = create_mcworld(world_dir, output_mcworld)

    assert result_path == output_mcworld
    assert output_mcworld.is_file()

    # Verify that files are placed at root of ZIP archive
    with zipfile.ZipFile(output_mcworld, "r") as zf:
        names = zf.namelist()
        assert "level.dat" in names
        assert "levelname.txt" in names
        assert "db/CURRENT" in names
        # Ensure no parent folder prefix in entry names
        for name in names:
            assert not name.startswith("source_world/")


def test_create_mcworld_file_exists_and_force(tmp_path: Path) -> None:
    world_dir = tmp_path / "source"
    world_dir.mkdir()
    (world_dir / "level.dat").write_bytes(b"DATA")

    output_mcworld = tmp_path / "target.mcworld"
    output_mcworld.write_bytes(b"EXISTING_CONTENT")

    # Without force should raise FileExistsError
    with pytest.raises(FileExistsError):
        create_mcworld(world_dir, output_mcworld, force=False)

    # With force should overwrite successfully
    create_mcworld(world_dir, output_mcworld, force=True)
    with zipfile.ZipFile(output_mcworld, "r") as zf:
        assert "level.dat" in zf.namelist()
