"""Backwards-compatibility bridge forwarding message constants to the i18n translation system."""

from typing import Any

from mc_xbox_dl.i18n import t

# Mapping of legacy constant names to i18n message keys
_CONST_TO_KEY: dict[str, str] = {
    "MSG_LOGIN_START": "login_start",
    "MSG_LOGIN_PROMPT": "login_prompt",
    "MSG_LOGIN_WAITING": "login_waiting",
    "MSG_LOGIN_SUCCESS": "login_success",
    "MSG_LOGOUT_SUCCESS": "logout_success",
    "MSG_WHOAMI": "whoami",
    "MSG_NOT_AUTHENTICATED": "not_authenticated",
    "MSG_LIST_FETCHING": "list_fetching",
    "MSG_LIST_EMPTY": "list_empty",
    "MSG_DOWNLOAD_START": "download_start",
    "MSG_DOWNLOAD_SUCCESS": "download_success",
    "MSG_DOWNLOAD_CANCELLED": "download_cancelled",
    "MSG_FILE_EXISTS": "file_exists",
    "MSG_DOWNLOAD_ALL_START": "download_all_start",
    "MSG_DOWNLOAD_ALL_START_INSTALL": "download_all_start_install",
    "MSG_DOWNLOAD_ALL_SKIPPED": "download_all_skipped",
    "MSG_DOWNLOAD_ALL_SKIPPED_INSTALL": "download_all_skipped_install",
    "MSG_DOWNLOAD_ALL_CURRENT": "download_all_current",
    "MSG_TARGET_OR_ALL_REQUIRED": "target_or_all_required",
    "MSG_INSTALLED_DIRECTLY": "installed_directly",
    "MSG_MINECRAFT_RUNNING_WARNING": "minecraft_running_warning",
    "MSG_DEBUG_SAVED": "debug_saved",
}


def __getattr__(name: str) -> Any:
    """Dynamically resolves legacy MSG_* constants via the active language translation catalog."""
    if name in _CONST_TO_KEY:
        return t(_CONST_TO_KEY[name])
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
