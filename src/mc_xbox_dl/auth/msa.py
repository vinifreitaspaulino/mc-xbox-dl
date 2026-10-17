"""Microsoft Account (MSA) authentication via Device Code Flow and token renewal."""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from mc_xbox_dl.config import CLIENT_ID, MSA_DEVICE_CODE_URL, MSA_SCOPE, MSA_TOKEN_URL
from mc_xbox_dl.errors import AccessDeniedError, NotAuthenticatedError
from mc_xbox_dl.http import HttpClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeviceCodeResponse:
    user_code: str
    device_code: str
    verification_uri: str
    expires_in: int
    interval: int


@dataclass(frozen=True)
class MsaTokenResponse:
    access_token: str
    refresh_token: str
    expires_in: int
    expires_at: str
    user_id: str | None = None


def request_device_code(
    http_client: HttpClient,
    client_id: str | None = None,
) -> DeviceCodeResponse:
    """Requests a new device code pair for authentication."""
    cid = client_id or CLIENT_ID
    payload = {
        "client_id": cid,
        "scope": MSA_SCOPE,
        "response_type": "device_code",
    }

    resp = http_client.request(
        "POST",
        MSA_DEVICE_CODE_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    if resp.is_error:
        raise NotAuthenticatedError(
            f"Failed to start Microsoft Account authentication "
            f"(HTTP {resp.status_code}): {resp.text}"
        )

    data = resp.json()
    return DeviceCodeResponse(
        user_code=data["user_code"],
        device_code=data["device_code"],
        verification_uri=data.get("verification_uri", "https://www.microsoft.com/link"),
        expires_in=int(data.get("expires_in", 900)),
        interval=int(data.get("interval", 5)),
    )


def poll_device_code(
    http_client: HttpClient,
    device_code: str,
    interval: int = 5,
    expires_in: int = 900,
    client_id: str | None = None,
) -> MsaTokenResponse:
    """
    Polls token endpoint until user approves login,
    a timeout expires, or a permanent error occurs.
    """
    cid = client_id or CLIENT_ID
    poll_interval = max(interval, 1)
    deadline = time.time() + expires_in

    payload = {
        "client_id": cid,
        "scope": MSA_SCOPE,
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "device_code": device_code,
    }

    while time.time() < deadline:
        time.sleep(poll_interval)

        resp = http_client.request(
            "POST",
            MSA_TOKEN_URL,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if resp.status_code == 200:
            data = resp.json()
            exp_seconds = int(data.get("expires_in", 3600))
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=exp_seconds)).isoformat()

            return MsaTokenResponse(
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token", ""),
                expires_in=exp_seconds,
                expires_at=expires_at,
                user_id=data.get("user_id"),
            )

        try:
            err_data = resp.json()
            err_code = err_data.get("error")
        except Exception:
            err_code = None

        if err_code == "authorization_pending":
            # User hasn't completed authorization in the browser yet
            continue
        elif err_code == "slow_down":
            poll_interval += 5
            continue
        elif err_code == "expired_token":
            raise NotAuthenticatedError("The login code has expired. Please initiate login again.")
        elif err_code == "access_denied":
            raise AccessDeniedError("Authorization was cancelled or denied on Microsoft account.")
        else:
            raise NotAuthenticatedError(
                f"Error during Microsoft authentication (HTTP {resp.status_code}): "
                f"{err_code or resp.text}"
            )

    raise NotAuthenticatedError("Timeout waiting for user authorization.")


def refresh_msa_token(
    http_client: HttpClient,
    refresh_token: str,
    client_id: str | None = None,
) -> MsaTokenResponse:
    """Renews MSA access_token using a refresh_token."""
    cid = client_id or CLIENT_ID
    payload = {
        "client_id": cid,
        "scope": MSA_SCOPE,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }

    resp = http_client.request(
        "POST",
        MSA_TOKEN_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    if resp.status_code == 200:
        data = resp.json()
        exp_seconds = int(data.get("expires_in", 3600))
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=exp_seconds)).isoformat()

        return MsaTokenResponse(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", refresh_token),
            expires_in=exp_seconds,
            expires_at=expires_at,
            user_id=data.get("user_id"),
        )

    try:
        err_data = resp.json()
        err_code = err_data.get("error")
    except Exception:
        err_code = None

    if err_code == "invalid_grant":
        raise NotAuthenticatedError("Microsoft account session expired or was revoked.")

    raise NotAuthenticatedError(
        f"Failed to refresh Microsoft account token (HTTP {resp.status_code}): "
        f"{err_code or resp.text}"
    )
