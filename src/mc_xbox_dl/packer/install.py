"""Direct installation of world directories into Minecraft Bedrock on Windows."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from mc_xbox_dl.errors import PackagingError
from mc_xbox_dl.packer.locator import resolve_minecraft_worlds_dir
from mc_xbox_dl.packer.mcworld import sanitize_filename


def get_minecraft_worlds_dir(
    install_dir: str | Path | None = None,
    interactive: bool = True,
) -> Path:
    """
    Locates official 'minecraftWorlds' directory for Minecraft Bedrock on Windows.
    Scans modern GDK Roaming paths and legacy UWP package directories.
    Allows manual override via argument or MC_WORLDS_DIR environment variable.
    """
    return resolve_minecraft_worlds_dir(install_dir=install_dir, interactive=interactive)


def install_world_dir(
    source_dir: Path,
    target_parent_dir: Path,
    world_name: str,
    world_id: str | None = None,
    force: bool = False,
) -> Path:
    """
    Extracts and installs validated world files into an exclusive subfolder
    within the 'minecraftWorlds' directory using safe atomic extraction.
    """
    target_parent_dir.mkdir(parents=True, exist_ok=True)

    # Derive safe, human-readable yet unique folder name
    clean_name = sanitize_filename(world_name.strip()) if world_name else ""
    if not clean_name and world_id:
        clean_name = sanitize_filename(world_id.replace(",savedgame", ""))
    if not clean_name:
        clean_name = "world"

    dest_dir = target_parent_dir / clean_name

    if dest_dir.exists():
        if force:
            shutil.rmtree(dest_dir)
        else:
            counter = 2
            while True:
                candidate = target_parent_dir / f"{clean_name} ({counter})"
                if not candidate.exists():
                    dest_dir = candidate
                    break
                counter += 1

    # Safe atomic extraction via staging directory on the same parent folder
    staging_dir = Path(tempfile.mkdtemp(prefix=".install_tmp_", dir=target_parent_dir))
    try:
        # Copy world contents to staging
        for item in source_dir.iterdir():
            if item.is_dir():
                shutil.copytree(item, staging_dir / item.name)
            else:
                shutil.copy2(item, staging_dir / item.name)

        # Integrity verification on staged files
        if not (staging_dir / "level.dat").is_file():
            raise PackagingError(
                "World installation failed: 'level.dat' missing from staged world."
            )
        if (source_dir / "levelname.txt").is_file() and not (
            staging_dir / "levelname.txt"
        ).is_file():
            raise PackagingError(
                "World installation failed: 'levelname.txt' missing from staged world."
            )
        if (source_dir / "db").is_dir() and not (staging_dir / "db").is_dir():
            raise PackagingError(
                "World installation failed: 'db/' directory missing from staged world."
            )

        # Atomic / safe rename to destination
        if dest_dir.exists() and force:
            shutil.rmtree(dest_dir)

        try:
            os.replace(staging_dir, dest_dir)
        except OSError:
            shutil.move(str(staging_dir), str(dest_dir))
    except Exception:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        raise

    return dest_dir


def is_minecraft_running() -> bool:
    """Checks whether the Minecraft Bedrock process (Minecraft.Windows.exe) is currently running."""
    if sys.platform != "win32":
        return False
    try:
        res = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Minecraft.Windows.exe", "/NH"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return "Minecraft.Windows.exe" in res.stdout
    except Exception:
        return False
