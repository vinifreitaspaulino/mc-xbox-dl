"""Centralized HTTP client with timeouts, retries, exponential backoff, and redacted debug dumps."""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from mc_xbox_dl.config import (
    ALLOWED_HOSTS,
    DEBUG_DIR,
    HTTP_CONNECT_TIMEOUT,
    HTTP_MAX_RETRIES,
    HTTP_READ_TIMEOUT,
)
from mc_xbox_dl.errors import AccessDeniedError, NetworkError
from mc_xbox_dl.redact import redact_data

logger = logging.getLogger(__name__)

# Execution-scoped counter for sequentially ordered debug dump filenames
_DUMP_COUNTER = 0


def _get_dump_filename() -> Path:
    global _DUMP_COUNTER
    _DUMP_COUNTER += 1
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return DEBUG_DIR / f"{now_str}-{_DUMP_COUNTER:03d}.json"


def _dump_debug_exchange(
    request: httpx.Request,
    response: httpx.Response | None,
    error: Exception | None = None,
) -> None:
    """Writes a redacted dump of the request, response, and error to disk."""
    try:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        dump_path = _get_dump_filename()

        # Prepare redacted request representation
        req_headers = dict(request.headers)
        req_body: Any = None
        if request.content:
            try:
                # Try parsing JSON if possible
                req_body = json.loads(request.content.decode("utf-8"))
            except Exception:
                # Truncate if plain text or binary
                raw_text = request.content.decode("utf-8", errors="replace")
                req_body = raw_text[:2000]

        req_info = {
            "method": request.method,
            "url": str(request.url),
            "headers": req_headers,
            "body": req_body,
        }

        resp_info: dict[str, Any] | None = None
        if response is not None:
            resp_headers = dict(response.headers)
            resp_body: Any = None
            if response.content:
                try:
                    resp_body = response.json()
                except Exception:
                    raw_text = response.text
                    resp_body = raw_text[:2000]

            resp_info = {
                "status_code": response.status_code,
                "headers": resp_headers,
                "body": resp_body,
            }

        dump_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request": redact_data(req_info),
            "response": redact_data(resp_info) if resp_info else None,
            "error": str(error) if error else None,
        }

        with open(dump_path, "w", encoding="utf-8") as f:
            json.dump(dump_data, f, indent=2, ensure_ascii=False)

        logger.debug("Debug dump saved at: %s", dump_path)
    except Exception as exc:
        logger.debug("Failed to write debug dump: %s", exc)


class HttpClient:
    """HTTP client with domain allowlist validation, timeouts, retries, and redacted dumps."""

    def __init__(self, debug: bool = False, max_retries: int = HTTP_MAX_RETRIES) -> None:
        self.debug = debug
        self.max_retries = max_retries
        self.client = httpx.Client(
            timeout=httpx.Timeout(
                connect=HTTP_CONNECT_TIMEOUT,
                read=HTTP_READ_TIMEOUT,
                write=HTTP_READ_TIMEOUT,
                pool=HTTP_CONNECT_TIMEOUT,
            ),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
            },
            follow_redirects=False,  # Explicit redirection control
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def _validate_host(self, url: str) -> None:
        """Ensures the requested URL belongs to the allowed list of Microsoft/Xbox domains."""
        parsed = urlparse(url)
        host = parsed.hostname
        if not host or host.lower() not in ALLOWED_HOSTS:
            raise AccessDeniedError(
                f"Unauthorized destination: {host}. "
                "Requests are restricted strictly to Microsoft/Xbox domains."
            )

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        data: Any = None,
        json_data: Any = None,
        content: Any = None,
        stream: bool = False,
        raise_for_status: bool = False,
    ) -> httpx.Response:
        self._validate_host(url)

        attempt = 0
        backoff = 1.0

        while True:
            attempt += 1
            response: httpx.Response | None = None
            try:
                req = self.client.build_request(
                    method=method,
                    url=url,
                    params=params,
                    headers=headers,
                    data=data,
                    json=json_data,
                    content=content,
                )

                if stream:
                    response = self.client.send(req, stream=True)
                else:
                    response = self.client.send(req)

                if self.debug:
                    _dump_debug_exchange(req, response)

                # Rate limiting handler (HTTP 429)
                if response.status_code == 429 and attempt <= self.max_retries:
                    retry_after = response.headers.get("Retry-After")
                    sleep_time = (
                        float(retry_after) if retry_after and retry_after.isdigit() else backoff
                    )
                    logger.warning(
                        "Rate limit reached (429). Retrying in %ss...",
                        sleep_time,
                    )
                    time.sleep(sleep_time)
                    backoff *= 2.0
                    continue

                # Transient server errors (5xx)
                if 500 <= response.status_code <= 599 and attempt <= self.max_retries:
                    logger.warning(
                        "Server unavailable (HTTP %s). Attempt %s/%s in %ss...",
                        response.status_code,
                        attempt,
                        self.max_retries,
                        backoff,
                    )
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue

                if raise_for_status:
                    if response.status_code in (401, 403):
                        raise AccessDeniedError(
                            f"Access denied by Microsoft servers (HTTP {response.status_code})."
                        )
                    if response.is_error:
                        response.raise_for_status()

                return response

            except httpx.TimeoutException as exc:
                if self.debug:
                    _dump_debug_exchange(req, response, exc)
                if attempt <= self.max_retries:
                    logger.warning(
                        "Request timed out. Attempt %s/%s in %ss...",
                        attempt,
                        self.max_retries,
                        backoff,
                    )
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise NetworkError("Connection to Microsoft servers timed out.") from exc

            except httpx.NetworkError as exc:
                if self.debug:
                    _dump_debug_exchange(req, response, exc)
                if attempt <= self.max_retries:
                    logger.warning(
                        "Transient network error. Attempt %s/%s in %ss...",
                        attempt,
                        self.max_retries,
                        backoff,
                    )
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise NetworkError(f"Network communication failure: {exc}") from exc
