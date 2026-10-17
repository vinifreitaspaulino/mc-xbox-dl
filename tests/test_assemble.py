"""Tests for atom unpacking and world reconstruction (packer/assemble.py)."""

import gzip
from pathlib import Path

import pytest

from mc_xbox_dl.errors import PackagingError
from mc_xbox_dl.packer.assemble import assemble_world, unpack_atom


def make_dummy_atom(rel_path: str, payload: bytes) -> bytes:
    path_bytes = rel_path.encode("utf-8")
    header = bytearray(b"\x00\x02\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00")
    header.append(len(path_bytes))
    return bytes(header) + path_bytes + payload


def test_unpack_atom_valid_file() -> None:
    atom = make_dummy_atom("db/000001.ldb", b"LEVELDB_RECORD_DATA")
    result = unpack_atom(atom)
    assert result is not None
    path, content = result
    assert path == "db/000001.ldb"
    assert content == b"LEVELDB_RECORD_DATA"


def test_unpack_atom_gzip_compressed_payload() -> None:
    original_data = b"COMPRESSED_LEVELDB_BLOCK_CONTENT" * 10
    compressed_payload = gzip.compress(original_data)
    assert compressed_payload.startswith(b"\x1f\x8b")

    atom = make_dummy_atom("db/000002.ldb", compressed_payload)
    result = unpack_atom(atom)
    assert result is not None
    path, content = result
    assert path == "db/000002.ldb"
    assert content == original_data


def test_unpack_atom_cloud_marker_skipped() -> None:
    atom = make_dummy_atom("CLOUD_TIMESTAMP", b"")
    result = unpack_atom(atom)
    assert result is None


def test_unpack_atom_short_header() -> None:
    assert unpack_atom(b"\x00\x01\x02") is None


def test_unpack_atom_path_traversal_dotdot() -> None:
    atom = make_dummy_atom("../secret.txt", b"evil")
    with pytest.raises(PackagingError, match="(?i)path traversal"):
        unpack_atom(atom)


def test_unpack_atom_path_traversal_absolute() -> None:
    atom = make_dummy_atom("/etc/passwd", b"evil")
    with pytest.raises(PackagingError, match="(?i)absolute"):
        unpack_atom(atom)


def test_unpack_atom_drive_letter() -> None:
    atom = make_dummy_atom("C:/Windows/system32", b"evil")
    with pytest.raises(PackagingError, match="(?i)invalid"):
        unpack_atom(atom)


def test_unpack_atom_windows_reserved() -> None:
    atom = make_dummy_atom("CON.txt", b"evil")
    with pytest.raises(PackagingError, match="(?i)reserved"):
        unpack_atom(atom)


def test_assemble_world_success(tmp_path: Path) -> None:
    atom1 = make_dummy_atom("levelname.txt", b"My Test World")
    atom2 = make_dummy_atom("db/CURRENT", b"MANIFEST-000001\n")
    atom3 = make_dummy_atom("CLOUD_TIMESTAMP", b"")

    written = assemble_world([atom1, atom2, atom3], tmp_path)

    assert len(written) == 2
    assert (tmp_path / "levelname.txt").read_text(encoding="utf-8") == "My Test World"
    assert (tmp_path / "db" / "CURRENT").read_bytes() == b"MANIFEST-000001\n"
