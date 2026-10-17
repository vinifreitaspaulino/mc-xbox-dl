"""Authentication orchestration: chained login, renewal, and session validation."""

import logging
from datetime import datetime, timedelta, timezone

from mc_xbox_dl.auth.msa import poll_device_code, refresh_msa_token, request_device_code
from mc_xbox_dl.auth.signer import generate_keypair
from mc_xbox_dl.auth.sisu import authenticate_device, authorize_sisu
from mc_xbox_dl.config import CLIENT_ID
from mc_xbox_dl.errors import NotAuthenticatedError
from mc_xbox_dl.http import HttpClient
from mc_xbox_dl.i18n import t
from mc_xbox_dl.session import (
    MsaTokens,
    SessionData,
    XblTokens,
    delete_session,
    load_session,
    save_session,
)

logger = logging.getLogger(__name__)

# Safety buffer for early token renewal (5 minutes)
EXPIRY_BUFFER_MINUTES = 5


def _is_expiring(iso_timestamp: str | None, buffer_minutes: int = EXPIRY_BUFFER_MINUTES) -> bool:
    """Checks whether an ISO timestamp is expired or expiring within the buffer window."""
    if not iso_timestamp:
        return True
    try:
        dt = datetime.fromisoformat(iso_timestamp)
        now = datetime.now(timezone.utc)
        return dt <= (now + timedelta(minutes=buffer_minutes))
    except Exception:
        return True


def login_flow(http_client: HttpClient, client_id: str | None = None) -> SessionData:
    """Executes the full Device Code login flow and persists session credentials."""
    cid = client_id or CLIENT_ID

    print(t("login_start"))
    dev_code_resp = request_device_code(http_client, client_id=cid)

    prompt = t(
        "login_prompt",
        url=dev_code_resp.verification_uri,
        code=dev_code_resp.user_code,
    )
    print(prompt, flush=True)

    msa_resp = poll_device_code(
        http_client,
        device_code=dev_code_resp.device_code,
        client_id=cid,
        interval=dev_code_resp.interval,
        expires_in=dev_code_resp.expires_in,
    )

    # Generate ephemeral ECDSA P-256 keypair and authenticate the device
    private_key = generate_keypair()
    device_token_resp = authenticate_device(http_client, private_key)

    # Acquire title-authorized XSTS authorization token via SISU
    xsts_resp = authorize_sisu(
        http_client,
        access_token=msa_resp.access_token,
        device_token=device_token_resp.token,
        private_key=private_key,
        client_id=cid,
    )

    session = SessionData(
        schema_version=1,
        created_at=datetime.now(timezone.utc).isoformat(),
        client_id=cid,
        auth_flow="sisu_device_code",
        msa=MsaTokens(
            refresh_token=msa_resp.refresh_token,
            access_token=msa_resp.access_token,
            access_expires_at=msa_resp.expires_at,
        ),
        xbl=XblTokens(
            user_hash=xsts_resp.user_hash,
            xuid=xsts_resp.xuid,
            xsts_token=xsts_resp.token,
            gamertag=xsts_resp.gamertag,
            xsts_expires_at=xsts_resp.not_after,
        ),
    )

    save_session(session)
    return session


def ensure_valid_session(http_client: HttpClient) -> SessionData:
    """
    Loads active session and silently refreshes MSA and XSTS tokens
    if they are expired or nearing expiration.
    """
    session = load_session()
    if not session:
        raise NotAuthenticatedError(t("not_authenticated"))

    # Check if XSTS or MSA token needs renewal
    needs_refresh = (
        session.auth_flow != "sisu_device_code"
        or _is_expiring(session.xbl.xsts_expires_at)
        or _is_expiring(session.msa.access_expires_at)
    )

    if not needs_refresh:
        return session

    logger.debug("Tokens expired or legacy flow detected. Silently refreshing session...")

    try:
        msa_resp = refresh_msa_token(
            http_client,
            session.msa.refresh_token,
            client_id=session.client_id,
        )

        private_key = generate_keypair()
        device_token_resp = authenticate_device(http_client, private_key)

        xsts_resp = authorize_sisu(
            http_client,
            access_token=msa_resp.access_token,
            device_token=device_token_resp.token,
            private_key=private_key,
            client_id=session.client_id,
        )

        updated_session = SessionData(
            schema_version=1,
            created_at=session.created_at,
            client_id=session.client_id,
            auth_flow="sisu_device_code",
            msa=MsaTokens(
                refresh_token=msa_resp.refresh_token,
                access_token=msa_resp.access_token,
                access_expires_at=msa_resp.expires_at,
            ),
            xbl=XblTokens(
                user_hash=xsts_resp.user_hash,
                xuid=xsts_resp.xuid,
                xsts_token=xsts_resp.token,
                gamertag=xsts_resp.gamertag or session.xbl.gamertag,
                xsts_expires_at=xsts_resp.not_after,
            ),
        )

        save_session(updated_session)
        return updated_session

    except NotAuthenticatedError as exc:
        # If refresh fails with invalid_grant, session must be wiped
        delete_session()
        raise NotAuthenticatedError(t("session_expired")) from exc
