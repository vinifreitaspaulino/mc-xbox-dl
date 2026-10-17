"""Session management and atomic persistence for session.json."""

import json
import logging
import os
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mc_xbox_dl import config
from mc_xbox_dl.errors import NotAuthenticatedError

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
SESSION_FILE = config.SESSION_FILE


@dataclass
class MsaTokens:
    refresh_token: str
    access_token: str | None = None
    access_expires_at: str | None = None


@dataclass
class XblTokens:
    user_hash: str
    xuid: str
    xsts_token: str
    gamertag: str | None = None
    xsts_expires_at: str | None = None


@dataclass
class SessionData:
    schema_version: int
    created_at: str
    client_id: str
    auth_flow: str
    msa: MsaTokens
    xbl: XblTokens

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionData":
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise NotAuthenticatedError(
                f"Unknown session schema version ({version}). A new login is required."
            )
        msa_data = data.get("msa", {})
        xbl_data = data.get("xbl", {})
        return cls(
            schema_version=SCHEMA_VERSION,
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            client_id=data.get("client_id", config.CLIENT_ID),
            auth_flow=data.get("auth_flow", "live_device_code"),
            msa=MsaTokens(
                refresh_token=msa_data.get("refresh_token", ""),
                access_token=msa_data.get("access_token"),
                access_expires_at=msa_data.get("access_expires_at"),
            ),
            xbl=XblTokens(
                user_hash=xbl_data.get("user_hash", ""),
                xuid=xbl_data.get("xuid", ""),
                xsts_token=xbl_data.get("xsts_token", ""),
                gamertag=xbl_data.get("gamertag"),
                xsts_expires_at=xbl_data.get("xsts_expires_at"),
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _restrict_file_permissions(file_path: Path) -> None:
    """Restricts file permissions to current user on Windows (via icacls) and POSIX (0o600)."""
    if os.name != "nt":
        try:
            os.chmod(file_path, 0o600)
        except OSError:
            pass
        return

    try:
        username = os.getenv("USERNAME")
        if not username:
            return
        # Remove inheritance and grant read/write access only to current user
        subprocess.run(
            ["icacls", str(file_path), "/inheritance:r", "/grant:r", f"{username}:(R,W)"],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except Exception as exc:
        logger.debug("Failed to set ACL permissions on %s: %s", file_path, exc)


def load_session(path: Path | None = None) -> SessionData | None:
    """
    Loads session data from disk.
    Returns None if file does not exist, schema is unknown, or JSON is corrupted.
    """
    target = path or config.SESSION_FILE
    if not target.exists():
        return None

    try:
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
        return SessionData.from_dict(data)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to parse session at %s: %s. Treating as missing.", target, exc)
        return None
    except NotAuthenticatedError:
        # Invalid schema version
        return None


def save_session(session: SessionData, path: Path | None = None) -> None:
    """
    Atomically writes session to disk (temporary file + os.replace)
    and restricts read/write permissions to current user.
    """
    target = path or config.SESSION_FILE
    target_dir = target.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    # Write to temporary file in the same directory for atomic replace
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=target_dir,
        delete=False,
        suffix=".tmp",
    ) as tmp_file:
        tmp_path = Path(tmp_file.name)
        json.dump(session.to_dict(), tmp_file, indent=2, ensure_ascii=False)

    try:
        _restrict_file_permissions(tmp_path)
        os.replace(tmp_path, target)
        _restrict_file_permissions(target)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def delete_session(path: Path | None = None) -> bool:
    """Deletes session file from disk. Returns True if file existed and was removed."""
    target = path or config.SESSION_FILE
    if target.exists():
        try:
            target.unlink()
            return True
        except OSError as exc:
            logger.warning("Error deleting session file %s: %s", target, exc)
            return False
    return False
