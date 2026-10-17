"""Structural validation of Minecraft Bedrock world files."""

import struct
from pathlib import Path


def validate_world_dir(world_dir: Path) -> tuple[bool, str | None]:
    """
    Validates the basic structural integrity of a Bedrock world directory.

    Mandatory integrity checks:
    - Presence of level.dat with plausible Bedrock NBT header (8 bytes: version + length).
    - Presence of levelname.txt.
    - Presence of db/CURRENT.
    - Presence of at least one db/MANIFEST-* file.

    Returns:
    - (True, None) if structure is valid.
    - (False, error_message) if any essential component is missing or corrupt.
    """
    if not world_dir.is_dir():
        return False, f"Path '{world_dir}' is not a valid directory."

    # 1. level.dat
    level_dat = world_dir / "level.dat"
    if not level_dat.is_file():
        return False, "Essential file 'level.dat' was not found at world root."

    level_bytes = level_dat.read_bytes()
    if len(level_bytes) < 9:
        return False, "File 'level.dat' is corrupt or has insufficient size."

    try:
        version, payload_len = struct.unpack("<II", level_bytes[:8])
        if version == 0 or payload_len == 0:
            return (
                False,
                f"Header in 'level.dat' is null (version={version}, length={payload_len}).",
            )
        # First byte of Bedrock NBT payload must be TAG_Compound (0x0A)
        if level_bytes[8] != 0x0A:
            return (
                False,
                f"Invalid NBT root in 'level.dat' (expected 0x0A, got {hex(level_bytes[8])}).",
            )
    except Exception as exc:
        return False, f"Failed to parse 'level.dat' header: {exc}"

    # 2. levelname.txt
    level_name = world_dir / "levelname.txt"
    if not level_name.is_file():
        return False, "File 'levelname.txt' was not found at world root."

    # 3. db/ directory
    db_dir = world_dir / "db"
    if not db_dir.is_dir():
        return False, "Database directory 'db/' was not found."

    # 4. db/CURRENT
    current_file = db_dir / "CURRENT"
    if not current_file.is_file():
        return False, "LevelDB file 'db/CURRENT' was not found."

    # 5. db/MANIFEST-*
    manifest_files = list(db_dir.glob("MANIFEST-*"))
    if not manifest_files:
        return False, "No LevelDB manifest files ('db/MANIFEST-*') were found."

    return True, None
