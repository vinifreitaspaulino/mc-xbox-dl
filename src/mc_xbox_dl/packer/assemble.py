"""Assembly and reconstruction of Minecraft Bedrock world files from raw cloud atoms."""

import gzip
import logging
from pathlib import Path, PurePosixPath

from mc_xbox_dl.errors import PackagingError

logger = logging.getLogger(__name__)

GZIP_MAGIC_BYTES = b"\x1f\x8b"

WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


def unpack_atom(atom_bytes: bytes) -> tuple[str, bytes] | None:
    """
    Decodes the binary header of an Xbox Connected Storage atom.

    Atom binary layout:
    - 13 bytes: initial header
    - 1 byte: length of the relative file path (path_len)
    - path_len bytes: UTF-8 relative path (e.g., 'level.dat', 'db/000052.log')
    - Remaining bytes: exact file payload contents

    Returns:
    - (relative_path, payload_bytes) if a valid world file.
    - None if internal cloud synchronization metadata (e.g. 'CLOUD_TIMESTAMP').

    Raises:
    - PackagingError if path violates security constraints (path traversal, reserved names).
    """
    if len(atom_bytes) < 14:
        return None

    path_len = atom_bytes[13]
    if len(atom_bytes) < 14 + path_len:
        return None

    raw_path = atom_bytes[14 : 14 + path_len].decode("utf-8", errors="replace")

    # Discard cloud sync metadata markers
    if raw_path.startswith("CLOUD_"):
        logger.debug("Skipping cloud metadata atom: %s", raw_path)
        return None

    # Normalization and path traversal defense
    clean_path = raw_path.replace("\\", "/").strip()
    if not clean_path or clean_path.startswith("/"):
        raise PackagingError(f"Invalid absolute or empty path in atom: {raw_path}")

    # Forbid colons (drive letters like C: or NTFS alternate data streams)
    if ":" in clean_path:
        raise PackagingError(f"Invalid character (:) in atom path: {raw_path}")

    posix_path = PurePosixPath(clean_path)
    for part in posix_path.parts:
        if part in ("..", "."):
            raise PackagingError(f"Path traversal attempt detected in atom: {raw_path}")
        stem = part.split(".")[0].upper()
        if stem in WINDOWS_RESERVED_NAMES:
            raise PackagingError(f"Windows reserved device name detected in atom: {raw_path}")

    payload = atom_bytes[14 + path_len :]
    if payload.startswith(GZIP_MAGIC_BYTES):
        try:
            payload = gzip.decompress(payload)
        except Exception as exc:
            raise PackagingError(
                f"Failed to decompress gzip payload in atom '{posix_path}': {exc}"
            ) from exc

    return str(posix_path), payload


def assemble_world(atoms: list[bytes], output_dir: Path) -> list[Path]:
    """
    Unpacks raw cloud atoms and writes files to the target directory,
    faithfully recreating the Bedrock world directory tree.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    written_files: list[Path] = []

    for atom in atoms:
        unpacked = unpack_atom(atom)
        if unpacked is None:
            continue

        rel_path, content = unpacked
        dest_file = output_dir / rel_path

        # Ensure destination file remains strictly within output_dir
        try:
            dest_file.resolve().relative_to(output_dir.resolve())
        except ValueError:
            raise PackagingError(f"File path escapes destination directory: {rel_path}") from None

        dest_file.parent.mkdir(parents=True, exist_ok=True)
        dest_file.write_bytes(content)
        written_files.append(dest_file)

    return written_files
