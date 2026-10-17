"""Automatic discovery and resolution of Minecraft Bedrock installation directories on Windows."""

import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

from mc_xbox_dl.errors import PackagingError
from mc_xbox_dl.i18n import t

logger = logging.getLogger(__name__)

# Official Package Identities
UWP_PACKAGE_NAME = "Microsoft.MinecraftUWP_8wekyb3d8bbwe"
BETA_PACKAGE_NAME = "Microsoft.MinecraftWindowsBeta_8wekyb3d8bbwe"


@dataclass(frozen=True)
class MinecraftProfile:
    """Represents a discovered Minecraft Bedrock user profile and world directory."""

    path: Path
    profile_type: str  # "gdk", "uwp", "uwp_beta", or "custom"
    user_id: str | None = None
    modified_time: float = 0.0


def find_minecraft_profiles() -> list[MinecraftProfile]:
    """
    Scans the system for valid Minecraft Bedrock world storage directories.
    Checks modern GDK (Roaming Users/<ID>) and legacy UWP (LocalAppData Packages).
    Returns profiles sorted by most recent modification time.
    """
    # Check custom environment variable override
    env_override = os.getenv("MC_WORLDS_DIR")
    if env_override:
        custom_path = Path(env_override).resolve()
        custom_path.mkdir(parents=True, exist_ok=True)
        mtime = custom_path.stat().st_mtime if custom_path.exists() else 0.0
        return [
            MinecraftProfile(
                path=custom_path,
                profile_type="custom",
                user_id="Custom",
                modified_time=mtime,
            )
        ]

    # Non-Windows check (unless testing with environment variables set)
    appdata_str = os.getenv("APPDATA")
    localappdata_str = os.getenv("LOCALAPPDATA")
    if sys.platform != "win32" and not (appdata_str or localappdata_str):
        return []

    profiles: list[MinecraftProfile] = []

    # 1. Primary Discovery: Modern GDK (Microsoft GDK / Roaming Users/<ID>)
    if appdata_str:
        gdk_users_dir = Path(appdata_str) / "Minecraft Bedrock" / "Users"
        if gdk_users_dir.is_dir():
            try:
                for entry in gdk_users_dir.iterdir():
                    # Only numeric 64-bit user directories; ignore "Shared" and non-numeric
                    if entry.is_dir() and entry.name.isdigit():
                        mojang_dir = entry / "games" / "com.mojang"
                        if mojang_dir.is_dir():
                            worlds_dir = mojang_dir / "minecraftWorlds"
                            worlds_dir.mkdir(parents=True, exist_ok=True)
                            mtime = worlds_dir.stat().st_mtime
                            profiles.append(
                                MinecraftProfile(
                                    path=worlds_dir,
                                    profile_type="gdk",
                                    user_id=entry.name,
                                    modified_time=mtime,
                                )
                            )
            except Exception as exc:
                logger.debug("Failed scanning GDK Users directory: %s", exc)

    # 2. Fallback Discovery: Legacy UWP (LocalAppData Packages)
    if localappdata_str:
        packages_dir = Path(localappdata_str) / "Packages"

        # Retail UWP Package
        uwp_mojang = packages_dir / UWP_PACKAGE_NAME / "LocalState" / "games" / "com.mojang"
        if uwp_mojang.is_dir():
            worlds_dir = uwp_mojang / "minecraftWorlds"
            worlds_dir.mkdir(parents=True, exist_ok=True)
            profiles.append(
                MinecraftProfile(
                    path=worlds_dir,
                    profile_type="uwp",
                    user_id="Retail",
                    modified_time=worlds_dir.stat().st_mtime,
                )
            )

        # Beta / Preview UWP Package
        beta_mojang = packages_dir / BETA_PACKAGE_NAME / "LocalState" / "games" / "com.mojang"
        if beta_mojang.is_dir():
            worlds_dir = beta_mojang / "minecraftWorlds"
            worlds_dir.mkdir(parents=True, exist_ok=True)
            profiles.append(
                MinecraftProfile(
                    path=worlds_dir,
                    profile_type="uwp_beta",
                    user_id="Beta/Preview",
                    modified_time=worlds_dir.stat().st_mtime,
                )
            )

    # Sort profiles by most recent modification time descending
    profiles.sort(key=lambda p: p.modified_time, reverse=True)
    return profiles


def prompt_select_profile(profiles: Sequence[MinecraftProfile]) -> MinecraftProfile:
    """Interactively prompts the user to select from multiple detected Minecraft profiles."""
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title=t("multiple_profiles_found"))
        table.add_column("#", justify="right", style="cyan")
        table.add_column(t("col_profile_type"), style="magenta")
        table.add_column(t("col_profile_user"), style="green")
        table.add_column(t("col_profile_path"), style="white")
        table.add_column(t("col_modified"), style="yellow")

        for idx, prof in enumerate(profiles, start=1):
            date_str = (
                datetime.fromtimestamp(prof.modified_time).strftime("%Y-%m-%d %H:%M")
                if prof.modified_time > 0
                else "-"
            )
            type_label = (
                "GDK"
                if prof.profile_type == "gdk"
                else ("UWP" if prof.profile_type == "uwp" else prof.profile_type.upper())
            )
            table.add_row(str(idx), type_label, prof.user_id or "-", str(prof.path), date_str)

        console.print(table)
    except Exception:
        print(f"\n{t('multiple_profiles_found')}")
        for idx, prof in enumerate(profiles, start=1):
            print(f" [{idx}] {prof.profile_type.upper()} ({prof.user_id or '-'}) -> {prof.path}")

    try:
        prompt_text = f"{t('multiple_profiles_choice', max_choice=len(profiles))} "
        choice = input(prompt_text).strip()
        if choice.isdigit():
            chosen = int(choice)
            if 1 <= chosen <= len(profiles):
                return profiles[chosen - 1]
    except (EOFError, KeyboardInterrupt):
        pass

    # Default fallback: most recently modified profile
    return profiles[0]


def resolve_minecraft_worlds_dir(
    install_dir: str | Path | None = None,
    interactive: bool = True,
) -> Path:
    """
    Resolves the target 'minecraftWorlds' directory.
    Uses explicit install_dir if provided, otherwise discovers GDK/UWP installations.
    """
    if install_dir:
        custom_dir = Path(install_dir).resolve()
        custom_dir.mkdir(parents=True, exist_ok=True)
        return custom_dir

    profiles = find_minecraft_profiles()
    if not profiles:
        raise PackagingError(t("err_minecraft_not_found"))

    if len(profiles) == 1:
        logger.debug("Single Minecraft Bedrock profile resolved: %s", profiles[0].path)
        return profiles[0].path

    # Multiple profiles discovered
    if not interactive:
        logger.info(t("multiple_profiles_auto", path=profiles[0].path))
        return profiles[0].path

    selected = prompt_select_profile(profiles)
    return selected.path
