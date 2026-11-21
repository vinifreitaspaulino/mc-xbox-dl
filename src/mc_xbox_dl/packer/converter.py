"""Bedrock to Java Edition world conversion using the official Chunker CLI."""

import logging
import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from mc_xbox_dl.config import (
    CHUNKER_LATEST_RELEASE_URL,
    DEFAULT_JAVA_TARGET_VERSION,
    get_chunker_jar,
)
from mc_xbox_dl.errors import ConversionError, McXboxDlError
from mc_xbox_dl.http import HttpClient
from mc_xbox_dl.i18n import t
from mc_xbox_dl.packer.assemble import GZIP_MAGIC_BYTES

logger = logging.getLogger(__name__)

MIN_JAVA_MAJOR_VERSION = 17
_CHUNKER_ASSET_PATTERN = re.compile(r"^chunker-cli-.*\.jar$", re.IGNORECASE)
_JAVA_VERSION_PATTERN = re.compile(
    r'(?:version\s+"|(?:openjdk|java)\s+)(\d+)(?:\.(\d+))?',
    re.IGNORECASE,
)
_NORMALIZED_FORMAT_PATTERN = re.compile(r"^JAVA_\d+_\d+(?:_\d+)?$")


def check_java_runtime() -> int:
    """
    Executes 'java -version' and validates that Java 17 or higher is installed.
    Returns the detected major Java version integer, or raises ConversionError.
    """
    try:
        res = subprocess.run(
            ["java", "-version"],
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError) as exc:
        raise ConversionError(t("err_java_not_found")) from exc

    combined_output = f"{res.stderr or ''}\n{res.stdout or ''}".strip()
    match = _JAVA_VERSION_PATTERN.search(combined_output)
    if not match:
        raise ConversionError(t("err_java_not_found"))

    first_num = int(match.group(1))
    second_num = int(match.group(2)) if match.group(2) is not None else 0
    major_version = second_num if (first_num == 1 and second_num > 0) else first_num

    if major_version < MIN_JAVA_MAJOR_VERSION:
        raise ConversionError(t("err_java_version_too_low", version=major_version))

    return major_version


def normalize_chunker_format(version_str: str) -> str:
    """
    Normalizes user-friendly Java version strings (e.g. '1.21.4', '1.20', 'JAVA_1_21_4')
    into Chunker CLI's expected format ('JAVA_1_21_4', 'JAVA_1_20').
    """
    cleaned = version_str.strip().upper()
    if not cleaned:
        raise ConversionError(
            t("err_chunker_failed", details="Target Java version cannot be empty.")
        )

    if cleaned.startswith("JAVA_"):
        cleaned = cleaned[5:]
    elif cleaned.startswith("V"):
        cleaned = cleaned[1:]

    normalized = "JAVA_" + re.sub(r"[.\-]+", "_", cleaned)
    if not _NORMALIZED_FORMAT_PATTERN.match(normalized):
        raise ConversionError(
            t(
                "err_chunker_failed",
                details=f"Invalid Java target version format: '{version_str}'.",
            )
        )

    return normalized


def ensure_chunker_jar(
    http_client: HttpClient,
    chunker_jar: Path | None = None,
    show_progress: bool = True,
) -> Path:
    """
    Ensures the Chunker CLI JAR file exists locally.
    If missing or empty, queries GitHub Releases for 'HiveGamesOSS/Chunker' and
    streams 'chunker-cli-*.jar' atomically to disk.
    """
    target_jar = chunker_jar or get_chunker_jar()
    if target_jar.is_file() and target_jar.stat().st_size > 0:
        return target_jar

    try:
        release_resp = http_client.request(
            "GET",
            CHUNKER_LATEST_RELEASE_URL,
            headers={"Accept": "application/vnd.github+json"},
            follow_redirects=True,
        )
    except McXboxDlError as exc:
        raise ConversionError(t("err_chunker_failed", details=str(exc))) from exc

    if release_resp.status_code != 200:
        raise ConversionError(
            t(
                "err_chunker_failed",
                details=f"GitHub Releases API returned HTTP {release_resp.status_code}.",
            )
        )

    try:
        release_data = release_resp.json()
    except Exception as exc:
        raise ConversionError(
            t("err_chunker_failed", details=f"Invalid JSON from GitHub Releases API: {exc}")
        ) from exc

    assets = release_data.get("assets", [])
    asset_name: str | None = None
    download_url: str | None = None

    if isinstance(assets, list):
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = asset.get("name", "")
            url = asset.get("browser_download_url", "")
            if isinstance(name, str) and isinstance(url, str):
                if _CHUNKER_ASSET_PATTERN.match(name) and url:
                    asset_name = name
                    download_url = url
                    break

    if not download_url or not asset_name:
        raise ConversionError(
            t(
                "err_chunker_failed",
                details="Could not find 'chunker-cli-*.jar' asset in the latest Chunker release.",
            )
        )

    target_jar.parent.mkdir(parents=True, exist_ok=True)
    part_file = target_jar.with_name(f"{target_jar.name}.part")

    print(t("chunker_downloading", name=asset_name))

    try:
        dl_resp = http_client.request(
            "GET",
            download_url,
            stream=True,
            follow_redirects=True,
        )
        try:
            if dl_resp.status_code != 200:
                raise ConversionError(
                    t(
                        "err_chunker_failed",
                        details=f"Failed to download Chunker JAR (HTTP {dl_resp.status_code}).",
                    )
                )

            total_bytes = int(dl_resp.headers.get("Content-Length", "0") or 0)
            bytes_written = 0

            with open(part_file, "wb") as f:
                if show_progress:
                    try:
                        from rich.progress import (
                            BarColumn,
                            DownloadColumn,
                            Progress,
                            TextColumn,
                            TimeRemainingColumn,
                        )

                        with Progress(
                            TextColumn("[bold cyan]{task.description}"),
                            BarColumn(),
                            DownloadColumn(),
                            TimeRemainingColumn(),
                        ) as progress:
                            task_id = progress.add_task(
                                t("chunker_download_progress"),
                                total=total_bytes if total_bytes > 0 else None,
                            )
                            for chunk in dl_resp.iter_bytes(chunk_size=65536):
                                if chunk:
                                    f.write(chunk)
                                    bytes_written += len(chunk)
                                    progress.update(task_id, advance=len(chunk))
                    except Exception:
                        total_kb = total_bytes // 1024 if total_bytes > 0 else 0
                        for chunk in dl_resp.iter_bytes(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
                                bytes_written += len(chunk)
                                dl_kb = bytes_written // 1024
                                print(
                                    t(
                                        "chunker_download_fallback",
                                        downloaded=dl_kb,
                                        total=total_kb or "?",
                                    ),
                                    end="",
                                    flush=True,
                                )
                        print()
                else:
                    for chunk in dl_resp.iter_bytes(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
                            bytes_written += len(chunk)
        finally:
            dl_resp.close()

        if bytes_written == 0 or not part_file.is_file() or part_file.stat().st_size == 0:
            raise ConversionError(
                t("err_chunker_failed", details="Downloaded Chunker JAR file is empty.")
            )

        os.replace(part_file, target_jar)
        print(t("chunker_downloaded", path=target_jar))
        return target_jar

    except ConversionError:
        raise
    except Exception as exc:
        raise ConversionError(t("err_chunker_failed", details=str(exc))) from exc
    finally:
        if part_file.exists():
            try:
                part_file.unlink()
            except OSError:
                pass


def validate_java_world_dir(java_world_dir: Path) -> tuple[bool, str | None]:
    """
    Validates that a converted Minecraft Java world directory contains:
    1. A gzip-compressed 'level.dat' file (starting with magic bytes 0x1F 0x8B).
    2. A 'region/' directory.
    """
    if not java_world_dir.is_dir():
        return False, f"Converted Java world path '{java_world_dir}' is not a directory."

    level_dat = java_world_dir / "level.dat"
    if not level_dat.is_file():
        return False, "Essential file 'level.dat' is missing from converted Java world."

    try:
        header = level_dat.read_bytes()[:2]
    except Exception as exc:
        return False, f"Could not read 'level.dat' in converted Java world: {exc}"

    if len(header) < 2 or header != GZIP_MAGIC_BYTES:
        return (
            False,
            "Invalid 'level.dat' in converted Java world (expected gzip header 0x1F 0x8B).",
        )

    region_dir = java_world_dir / "region"
    if not region_dir.is_dir():
        return False, "Region directory 'region/' is missing from converted Java world."

    return True, None


def convert_bedrock_to_java(
    bedrock_world_dir: Path,
    output_java_dir: Path,
    target_format: str = DEFAULT_JAVA_TARGET_VERSION,
    chunker_jar: Path | None = None,
    memory_limit: str | None = None,
    force: bool = False,
    http_client: HttpClient | None = None,
) -> Path:
    """
    Converts a Bedrock world directory to a Minecraft Java Edition world directory
    using Chunker CLI, validates the output structure, and moves it atomically to
    output_java_dir (resolving unique '(2)', '(3)' suffixes if force=False).
    """
    check_java_runtime()
    normalized_format = normalize_chunker_format(target_format)

    jar_path = chunker_jar or get_chunker_jar()
    if not (jar_path.is_file() and jar_path.stat().st_size > 0):
        if http_client is not None:
            jar_path = ensure_chunker_jar(http_client, chunker_jar=jar_path)
        else:
            with HttpClient() as temp_client:
                jar_path = ensure_chunker_jar(temp_client, chunker_jar=jar_path)

    parent_dir = output_java_dir.parent
    parent_dir.mkdir(parents=True, exist_ok=True)

    dest_dir = output_java_dir
    if dest_dir.exists() and not force:
        base_name = output_java_dir.name
        counter = 2
        while True:
            candidate = parent_dir / f"{base_name} ({counter})"
            if not candidate.exists():
                dest_dir = candidate
                break
            counter += 1

    staging_java_dir = Path(tempfile.mkdtemp(prefix=".chunker_tmp_", dir=parent_dir))
    try:
        cmd = [
            "java",
            *([f"-Xmx{memory_limit}"] if memory_limit else []),
            "-jar",
            str(jar_path),
            "-i",
            str(bedrock_world_dir),
            "-o",
            str(staging_java_dir),
            "-f",
            normalized_format,
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )
        except (FileNotFoundError, OSError) as exc:
            raise ConversionError(t("err_java_not_found")) from exc

        if proc.returncode != 0:
            err_output = (proc.stderr or proc.stdout or f"exit code {proc.returncode}").strip()
            raise ConversionError(t("err_chunker_failed", details=err_output))

        is_valid, err_msg = validate_java_world_dir(staging_java_dir)
        if not is_valid:
            raise ConversionError(t("err_chunker_failed", details=err_msg or "Invalid Java world"))

        if dest_dir.exists() and force:
            shutil.rmtree(dest_dir)

        try:
            os.replace(staging_java_dir, dest_dir)
        except OSError:
            shutil.move(str(staging_java_dir), str(dest_dir))

        return dest_dir

    except Exception:
        if staging_java_dir.exists():
            shutil.rmtree(staging_java_dir, ignore_errors=True)
        raise


def get_java_saves_dir(custom_dir: str | Path | None = None) -> Path:
    """
    Resolves the local Minecraft Java Edition 'saves' directory across Windows and Linux:
    - Explicit custom_dir or MC_JAVA_SAVES_DIR environment variable override.
    - Windows: %APPDATA%\\.minecraft\\saves
    - Linux: ~/.minecraft/saves or Flatpak ~/.var/app/com.mojang.Minecraft/data/minecraft/saves
    Raises ConversionError if the parent .minecraft directory does not exist.
    """
    override = custom_dir or os.getenv("MC_JAVA_SAVES_DIR")
    if override:
        resolved = Path(override).expanduser().resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved

    system_name = platform.system()
    if system_name == "Windows":
        appdata = os.getenv("APPDATA")
        base_appdata = Path(appdata) if appdata else (Path.home() / "AppData" / "Roaming")
        mc_dir = base_appdata / ".minecraft"
        if mc_dir.is_dir():
            saves_dir = mc_dir / "saves"
            saves_dir.mkdir(parents=True, exist_ok=True)
            return saves_dir
        raise ConversionError(t("err_java_saves_not_found"))

    # Linux and other POSIX systems
    home = Path.home()
    standard_mc_dir = home / ".minecraft"
    if standard_mc_dir.is_dir():
        saves_dir = standard_mc_dir / "saves"
        saves_dir.mkdir(parents=True, exist_ok=True)
        return saves_dir

    flatpak_mc_dir = home / ".var" / "app" / "com.mojang.Minecraft" / "data" / "minecraft"
    if flatpak_mc_dir.is_dir():
        saves_dir = flatpak_mc_dir / "saves"
        saves_dir.mkdir(parents=True, exist_ok=True)
        return saves_dir

    raise ConversionError(t("err_java_saves_not_found"))
