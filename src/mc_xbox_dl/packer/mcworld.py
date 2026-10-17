"""Generation and packaging of .mcworld files (ZIP root layout)."""

import os
import re
import zipfile
from pathlib import Path

from mc_xbox_dl.packer.assemble import WINDOWS_RESERVED_NAMES


def sanitize_filename(name: str) -> str:
    """
    Sanitizes a world name for safe usage as a Windows filename.
    Strips illegal characters, boundary punctuation, and reserved device names.
    """
    # Remove invalid Windows filename characters: < > : " / \ | ? * and ASCII controls
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)
    # Strip leading/trailing dots and spaces
    cleaned = cleaned.strip(". ")

    if not cleaned:
        return "World"

    # Check Windows reserved device names (CON, PRN, AUX, etc.)
    stem = cleaned.split(".")[0].upper()
    if stem in WINDOWS_RESERVED_NAMES:
        cleaned = f"{cleaned}_world"

    # Truncate length to 100 characters
    return cleaned[:100].rstrip(". ")


def resolve_unique_filepath(output_dir: Path, base_name: str, suffix: str = ".mcworld") -> Path:
    """
    Returns a unique file path within output_dir to prevent collisions
    between distinct worlds sharing identical names.
    Example: World.mcworld, World (2).mcworld, World (3).mcworld, etc.
    """
    clean_name = sanitize_filename(base_name)
    candidate = output_dir / f"{clean_name}{suffix}"
    if not candidate.exists():
        return candidate

    counter = 2
    while True:
        candidate = output_dir / f"{clean_name} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def create_mcworld(world_dir: Path, output_file: Path, force: bool = False) -> Path:
    """
    Packages the contents of world_dir into a .mcworld ZIP archive with all
    files positioned directly at the root of the archive.
    Employs atomic writing via a temporary .part file.
    """
    if output_file.exists() and not force:
        raise FileExistsError(f"Destination file already exists: {output_file}")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    part_file = output_file.with_name(f"{output_file.name}.part")

    try:
        with zipfile.ZipFile(part_file, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(world_dir):
                for file_name in files:
                    full_path = Path(root) / file_name
                    arcname = full_path.relative_to(world_dir).as_posix()
                    zf.write(full_path, arcname)

        # Atomic replacement
        if output_file.exists():
            os.remove(output_file)
        os.replace(part_file, output_file)
        return output_file

    finally:
        if part_file.exists():
            try:
                os.remove(part_file)
            except OSError:
                pass
