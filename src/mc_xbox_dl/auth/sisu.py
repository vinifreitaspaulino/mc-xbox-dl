"""Acquiring Device Token and SISU authorization for Xbox Live titles."""

import json
import logging
import uuid
from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric import ec

from mc_xbox_dl.auth.signer import compute_signature, export_proof_key
from mc_xbox_dl.auth.xbl import XstsToken, _extract_xui_claims
from mc_xbox_dl.config import CLIENT_ID, XBL_DEVICE_AUTH_URL, XBL_SISU_AUTH_URL
from mc_xbox_dl.errors import AccessDeniedError
from mc_xbox_dl.http import HttpClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeviceToken:
    """Xbox Live Device Authentication Token."""

    token: str
    id: str


def authenticate_device(
    http_client: HttpClient,
    private_key: ec.EllipticCurvePrivateKey,
    device_id: str | None = None,
    device_type: str = "Android",
    version: str = "15.0",
) -> DeviceToken:
    """
    Registers/authenticates the device at device.auth.xboxlive.com.
    Returns the generated DeviceToken.
    """
    dev_id = device_id or f"{{{str(uuid.uuid4()).upper()}}}"
    proof_key = export_proof_key(private_key)

    payload = {
        "Properties": {
            "AuthMethod": "ProofOfPossession",
            "Id": dev_id,
            "DeviceType": device_type,
            "SerialNumber": dev_id,
            "Version": version,
            "ProofKey": proof_key,
        },
        "RelyingParty": "http://auth.xboxlive.com",
        "TokenType": "JWT",
    }

    body = json.dumps(payload, separators=(",", ":"))
    signature = compute_signature(
        url=XBL_DEVICE_AUTH_URL,
        method="POST",
        body=body,
        private_key=private_key,
    )

    resp = http_client.request(
        "POST",
        XBL_DEVICE_AUTH_URL,
        content=body.encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Signature": signature,
            "x-xbl-contract-version": "1",
        },
    )

    if resp.is_error:
        raise AccessDeniedError(
            f"Failed to authenticate Xbox Live device (HTTP {resp.status_code}): {resp.text}"
        )

    data = resp.json()
    token = data.get("Token")
    if not token:
        raise AccessDeniedError("Device authentication response does not contain Token.")

    return DeviceToken(token=token, id=dev_id)


def authorize_sisu(
    http_client: HttpClient,
    access_token: str,
    device_token: str,
    private_key: ec.EllipticCurvePrivateKey,
    client_id: str | None = None,
) -> XstsToken:
    """
    Performs SISU authorization to obtain the AuthorizationToken (Title-authorized XSTS)
    required for Minecraft Connected Storage access.
    """
    app_id = client_id or CLIENT_ID
    proof_key = export_proof_key(private_key)

    token_val = access_token
    if not (token_val.startswith("t=") or token_val.startswith("d=")):
        token_val = f"t={token_val}"

    payload = {
        "AccessToken": token_val,
        "AppId": app_id,
        "DeviceToken": device_token,
        "Sandbox": "RETAIL",
        "SiteName": "user.auth.xboxlive.com",
        "UseModernGamertag": True,
        "ProofKey": proof_key,
    }

    body = json.dumps(payload, separators=(",", ":"))
    signature = compute_signature(
        url=XBL_SISU_AUTH_URL,
        method="POST",
        body=body,
        private_key=private_key,
    )

    resp = http_client.request(
        "POST",
        XBL_SISU_AUTH_URL,
        content=body.encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Signature": signature,
            "x-xbl-contract-version": "1",
        },
    )

    if resp.is_error:
        raise AccessDeniedError(
            f"Failed SISU authorization for Minecraft (HTTP {resp.status_code}): {resp.text}"
        )

    data = resp.json()
    auth_tok_data = data.get("AuthorizationToken")
    if not auth_tok_data or "Token" not in auth_tok_data:
        raise AccessDeniedError("SISU response does not contain a valid AuthorizationToken.")

    token = auth_tok_data["Token"]
    not_after = auth_tok_data.get("NotAfter", "")

    claims = _extract_xui_claims(auth_tok_data)
    if not claims:
        # Fall back to root claims if not nested inside AuthorizationToken
        claims = _extract_xui_claims(data)

    if not claims:
        raise AccessDeniedError("SISU response does not contain user claims.")

    user_claim = claims[0]
    user_hash = user_claim.get("uhs", "")
    xuid = user_claim.get("xid", "")
    gamertag = user_claim.get("gtg") or user_claim.get("mgt")

    return XstsToken(
        token=token,
        user_hash=user_hash,
        xuid=xuid,
        gamertag=gamertag,
        not_after=not_after,
    )
