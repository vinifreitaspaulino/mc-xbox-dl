"""Configuration constants and filesystem path resolution."""

import os
from pathlib import Path

import platformdirs

APP_NAME = "mc-xbox-dl"

DATA_DIR: Path = Path(
    platformdirs.user_config_dir(
        appname=APP_NAME, appauthor=False, roaming=True, ensure_exists=True
    )
)
DEBUG_DIR: Path = DATA_DIR / "debug"
SESSION_FILE: Path = DATA_DIR / "session.json"
DEFAULT_SETTINGS_FILE: Path = DATA_DIR / "settings.json"


def get_settings_file() -> Path:
    """Returns the path to the persistent settings JSON file."""
    custom_path = os.getenv("MC_XBOX_DL_SETTINGS_FILE")
    if custom_path:
        return Path(custom_path)
    return DEFAULT_SETTINGS_FILE


SETTINGS_FILE: Path = get_settings_file()


# Credentials and Service Configuration Identifiers
DEFAULT_CLIENT_ID = "0000000048183522"  # Minecraft Bedrock Android
CLIENT_ID: str = os.getenv("MC_XBOX_DL_CLIENT_ID", DEFAULT_CLIENT_ID)

DEFAULT_SCID = "00000000-0000-0000-0000-00006cfa0c1e"
SCID: str = os.getenv("MC_XBOX_DL_SCID", DEFAULT_SCID)

DEFAULT_PFN = "Microsoft.186805A1E9E_8wekyb3d8bbwe"
PFN: str = os.getenv("MC_XBOX_DL_PFN", DEFAULT_PFN)

DEFAULT_TITLE_ID = 1828326430
TITLE_ID: int = int(os.getenv("MC_XBOX_DL_TITLE_ID", str(DEFAULT_TITLE_ID)))

DEFAULT_RELYING_PARTY = "http://xboxlive.com"
RELYING_PARTY: str = os.getenv("MC_XBOX_DL_RELYING_PARTY", DEFAULT_RELYING_PARTY)

# Official Microsoft / Xbox Endpoints
MSA_DEVICE_CODE_URL = "https://login.live.com/oauth20_connect.srf"
MSA_TOKEN_URL = "https://login.live.com/oauth20_token.srf"
MSA_SCOPE = "service::user.auth.xboxlive.com::MBI_SSL"

XBL_USER_AUTH_URL = "https://user.auth.xboxlive.com/user/authenticate"
XBL_DEVICE_AUTH_URL = "https://device.auth.xboxlive.com/device/authenticate"
XBL_SISU_AUTH_URL = "https://sisu.xboxlive.com/authorize"
XBL_XSTS_AUTH_URL = "https://xsts.auth.xboxlive.com/xsts/authorize"
TITLE_STORAGE_BASE_URL = "https://titlestorage.xboxlive.com"

# Authorized network domains for safety checks
ALLOWED_HOSTS: set[str] = {
    "login.live.com",
    "login.microsoftonline.com",
    "user.auth.xboxlive.com",
    "device.auth.xboxlive.com",
    "sisu.xboxlive.com",
    "xsts.auth.xboxlive.com",
    "titlestorage.xboxlive.com",
}

# Network timeouts (in seconds) and retry limits
HTTP_CONNECT_TIMEOUT = 10.0
HTTP_READ_TIMEOUT = 60.0
HTTP_MAX_RETRIES = 3

# Rate limiting and pacing (in seconds)
DOWNLOAD_INTER_WORLD_DELAY = 1.5

# World listing cache configuration (5 minutes TTL)
DEFAULT_WORLDS_CACHE_TTL = 300
DEFAULT_CACHE_FILE: Path = DATA_DIR / "cache.json"


def get_cache_file() -> Path:
    """Returns the path to the persistent cache JSON file."""
    custom_path = os.getenv("MC_XBOX_DL_CACHE_FILE")
    if custom_path:
        return Path(custom_path)
    return DATA_DIR / "cache.json"


CACHE_FILE: Path = get_cache_file()

# Default maximum cloud world size limit (2 GB)
MAX_WORLD_SIZE_BYTES = 2 * 1024 * 1024 * 1024
