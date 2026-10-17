"""Xbox Live authentication: acquiring User Token (XAU) and XSTS Token."""

import logging
from dataclasses import dataclass
from typing import Any

from mc_xbox_dl.config import RELYING_PARTY, XBL_USER_AUTH_URL, XBL_XSTS_AUTH_URL
from mc_xbox_dl.errors import AccessDeniedError, NotAuthenticatedError
from mc_xbox_dl.http import HttpClient
from mc_xbox_dl.i18n import t

logger = logging.getLogger(__name__)

# Known XSTS authorization error messages
XERR_MESSAGES = {
    2148916233: (
        "This Microsoft account does not have an Xbox Live profile. "
        "Visit https://xbox.com to create one."
    ),
    2148916235: "This account is suspended or banned from Xbox Live.",
    2148916236: "This account requires age verification or proof of majority.",
    2148916237: "This account has reached its family screen time limit.",
    2148916238: ("Child account must be added to a Microsoft family by a parent or guardian."),
}


@dataclass(frozen=True)
class XblUserToken:
    """Xbox Live User Token (XAU)."""

    token: str
    user_hash: str
    not_after: str


@dataclass(frozen=True)
class XstsToken:
    """XSTS authorization token for a targeted relying party."""

    token: str
    user_hash: str
    xuid: str
    gamertag: str | None
    not_after: str


def _extract_xui_claims(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Safely extracts the 'xui' claims list from DisplayClaims (either dict or list)."""
    raw_claims = data.get("DisplayClaims", {})
    if isinstance(raw_claims, list) and raw_claims:
        raw_claims = raw_claims[0]
    if isinstance(raw_claims, dict):
        return raw_claims.get("xui", [])
    return []


def authenticate_user_token(http_client: HttpClient, access_token: str) -> XblUserToken:
    """
    Exchanges a Microsoft Account (MSA) access token for an Xbox Live User Token (XAU).
    Attempts prefix 't=' first (default for login.live.com) with 'd=' as fallback.
    """
    prefixes = (
        [""] if (access_token.startswith("d=") or access_token.startswith("t=")) else ["t=", "d="]
    )

    last_resp = None
    for prefix in prefixes:
        payload = {
            "RelyingParty": "http://auth.xboxlive.com",
            "TokenType": "JWT",
            "Properties": {
                "AuthMethod": "RPS",
                "SiteName": "user.auth.xboxlive.com",
                "RpsTicket": f"{prefix}{access_token}",
            },
        }

        resp = http_client.request(
            "POST",
            XBL_USER_AUTH_URL,
            json_data=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "x-xbl-contract-version": "1",
            },
        )
        last_resp = resp

        if not resp.is_error:
            data = resp.json()
            token = data["Token"]
            not_after = data.get("NotAfter", "")

            claims = _extract_xui_claims(data)
            if not claims or "uhs" not in claims[0]:
                raise NotAuthenticatedError("Xbox Live response does not contain user hash (uhs).")

            user_hash = claims[0]["uhs"]
            return XblUserToken(token=token, user_hash=user_hash, not_after=not_after)

    error_text = last_resp.text if last_resp else "Empty response"
    status_code = last_resp.status_code if last_resp else 401
    raise NotAuthenticatedError(
        f"Failed to authenticate user on Xbox Live (HTTP {status_code}): {error_text}"
    )


def authorize_xsts(
    http_client: HttpClient,
    user_token: str,
    relying_party: str | None = None,
) -> XstsToken:
    """Exchanges User Token for an XSTS token for the target RelyingParty."""
    rp = relying_party or RELYING_PARTY
    payload = {
        "RelyingParty": rp,
        "TokenType": "JWT",
        "Properties": {
            "UserTokens": [user_token],
            "SandboxId": "RETAIL",
        },
    }

    resp = http_client.request(
        "POST",
        XBL_XSTS_AUTH_URL,
        json_data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-xbl-contract-version": "1",
        },
    )

    if resp.status_code == 401:
        try:
            err_data = resp.json()
            xerr = err_data.get("XErr")
            if xerr and int(xerr) in XERR_MESSAGES:
                err_key = f"xerr_{int(xerr)}"
                msg = t(err_key)
                if msg == err_key:
                    msg = XERR_MESSAGES[int(xerr)]
                raise AccessDeniedError(msg)
        except (ValueError, KeyError):
            pass
        raise AccessDeniedError(f"XSTS authorization denied by Xbox Live (HTTP 401): {resp.text}")

    if resp.is_error:
        raise AccessDeniedError(
            f"Failed to obtain XSTS authorization (HTTP {resp.status_code}): {resp.text}"
        )

    data = resp.json()
    token = data["Token"]
    not_after = data.get("NotAfter", "")

    claims = _extract_xui_claims(data)
    if not claims:
        raise AccessDeniedError("XSTS response does not contain user claims.")

    user_claim = claims[0]
    user_hash = user_claim.get("uhs", "")
    xuid = user_claim.get("xid", "")
    gamertag = user_claim.get("gtg")

    return XstsToken(
        token=token,
        user_hash=user_hash,
        xuid=xuid,
        gamertag=gamertag,
        not_after=not_after,
    )
