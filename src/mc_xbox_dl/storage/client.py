import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mc_xbox_dl.config import (
    DEFAULT_WORLDS_CACHE_TTL,
    PFN,
    SCID,
    TITLE_STORAGE_BASE_URL,
    get_cache_file,
)
from mc_xbox_dl.errors import (
    AccessDeniedError,
    NetworkError,
    RateLimitError,
    WorldNotFoundError,
)
from mc_xbox_dl.http import HttpClient
from mc_xbox_dl.session import SessionData
from mc_xbox_dl.storage.models import BlobRef, WorldInfo

logger = logging.getLogger(__name__)


class StorageClient:
    """Client for query and download operations on Xbox Live Connected Storage."""

    def __init__(
        self,
        http_client: HttpClient,
        session: SessionData,
        scid: str | None = None,
        pfn: str | None = None,
    ) -> None:
        self.http_client = http_client
        self.session = session
        self.scid = scid or SCID
        self.pfn = pfn or PFN
        self.xuid = session.xbl.xuid
        self.user_hash = session.xbl.user_hash
        self.xsts_token = session.xbl.xsts_token

    def _headers(self) -> dict[str, str]:
        """Generates authentication headers required by the Title Storage API."""
        headers = {
            "Authorization": f"XBL3.0 x={self.user_hash};{self.xsts_token}",
            "x-xbl-contract-version": "1",
            "Accept": "application/json, */*",
        }
        if self.pfn:
            headers["x-xbl-pfn"] = self.pfn
        return headers

    def _read_cache(self, ttl: int = DEFAULT_WORLDS_CACHE_TTL) -> list[dict[str, Any]] | None:
        """Reads cached container list if valid and unexpired."""
        try:
            cache_file = get_cache_file()
            if not cache_file.exists():
                return None
            with open(cache_file, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if not isinstance(payload, dict):
                return None
            cached_xuid = payload.get("xuid")
            cached_scid = payload.get("scid")
            timestamp = payload.get("timestamp", 0)
            if cached_xuid != self.xuid or cached_scid != self.scid:
                return None
            if ttl <= 0 or (time.time() - timestamp) >= ttl:
                return None
            items = payload.get("items")
            if isinstance(items, list):
                logger.debug("Using cached cloud worlds listing (%d items)", len(items))
                return items
        except Exception as exc:
            logger.debug("Failed to read cache file: %s", exc)
        return None

    def _write_cache(self, items: list[dict[str, Any]]) -> None:
        """Writes container list to cache atomically."""
        try:
            cache_file = get_cache_file()
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "xuid": self.xuid,
                "scid": self.scid,
                "timestamp": time.time(),
                "items": items,
            }
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=cache_file.parent,
                delete=False,
                suffix=".tmp",
            ) as tmp_file:
                json.dump(payload, tmp_file, indent=2, ensure_ascii=False)
                tmp_path = Path(tmp_file.name)
            os.replace(tmp_path, cache_file)
            logger.debug("Cached cloud worlds listing (%d items)", len(items))
        except Exception as exc:
            logger.debug("Failed to write cache file: %s", exc)

    def list_worlds(self, use_cache: bool = True) -> list[WorldInfo]:
        """Queries Xbox Cloud and returns the list of synchronized worlds."""
        raw_items: list[dict[str, Any]] | None = None
        if use_cache:
            raw_items = self._read_cache()

        if raw_items is None:
            raw_items = self._fetch_containers()
            if use_cache:
                self._write_cache(raw_items)

        if not raw_items:
            return []

        worlds: list[WorldInfo] = []
        for idx, item in enumerate(raw_items, start=1):
            world_info = self._parse_world_item(idx, item)
            worlds.append(world_info)

        # Sort descending by modification date (most recent first)
        # Undated worlds placed at the end
        worlds.sort(
            key=lambda w: w.modified_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

        # Re-index from 1 to N after sorting
        reindexed_worlds = [
            WorldInfo(
                index=i,
                world_id=w.world_id,
                name=w.name,
                modified_at=w.modified_at,
                size_bytes=w.size_bytes,
                thumbnail_available=w.thumbnail_available,
                container_name=w.container_name,
            )
            for i, w in enumerate(worlds, start=1)
        ]

        return reindexed_worlds

    def _fetch_containers(self) -> list[dict[str, Any]]:
        """
        Fetches the list of cloud containers/blobs.
        Prioritizes the primary Minecraft Bedrock Xbox Connected Storage endpoint.
        """
        # Primary Connected Storage endpoint for Minecraft Xbox SCID
        primary_url = (
            f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({self.xuid})/scids/{self.scid}"
        )
        logger.debug("Querying Connected Storage at: %s", primary_url)
        resp = self.http_client.request("GET", primary_url, headers=self._headers())

        if resp.status_code == 429:
            raise RateLimitError("Xbox Live Connected Storage rate limit reached (HTTP 429).")

        if resp.status_code in (401, 403):
            raise AccessDeniedError(
                f"Access denied to Connected Storage (HTTP {resp.status_code}). "
                "Ensure your account has proper permissions and cloud saves."
            )

        if resp.status_code == 200:
            try:
                data = resp.json()
                blobs = data.get("blobs")
                if isinstance(blobs, list):
                    # Filter only entries representing world saves
                    world_blobs = [
                        b
                        for b in blobs
                        if isinstance(b, dict) and b.get("fileName", "").startswith("WORLD")
                    ]
                    if not world_blobs and blobs:
                        world_blobs = [
                            b
                            for b in blobs
                            if isinstance(b, dict)
                            and not b.get("fileName", "").startswith("SETTINGS")
                        ]
                    return world_blobs
                return self._extract_items_list(data)
            except Exception as exc:
                logger.warning("Response from %s is not valid JSON: %s", primary_url, exc)

        if resp.status_code in (401, 403):
            raise AccessDeniedError(
                f"Access denied to Connected Storage (HTTP {resp.status_code}). "
                "Ensure your account has proper permissions and cloud saves."
            )

        # Fallback routes for alternative/legacy endpoints (mock and platform variants)
        candidate_paths = [
            f"/connectedstorage/users/xuid({self.xuid})/scids/{self.scid}/containers",
            f"/connectedstorage/users/xuid({self.xuid})/scids/{self.scid}/containers.json",
            f"/users/xuid({self.xuid})/scids/{self.scid}/data?maxItems=100",
            f"/untrustedplatform/users/xuid({self.xuid})/scids/{self.scid}/data/",
        ]

        for path in candidate_paths:
            url = f"{TITLE_STORAGE_BASE_URL}{path}"
            logger.debug("Attempting query fallback at: %s", url)

            fb_resp = self.http_client.request(
                "GET",
                url,
                headers=self._headers(),
            )

            if fb_resp.status_code == 200:
                try:
                    data = fb_resp.json()
                    return self._extract_items_list(data)
                except Exception as exc:
                    logger.warning("Response from %s is not valid JSON: %s", url, exc)
                    continue

            if fb_resp.status_code == 404:
                try:
                    err_json = fb_resp.json()
                    if err_json.get("code") == 2005:
                        logger.info("No data found in Connected Storage (code 2005).")
                        return []
                except Exception:
                    pass

            if fb_resp.status_code in (401, 403):
                raise AccessDeniedError(
                    f"Access denied to Connected Storage (HTTP {fb_resp.status_code}). "
                    "Ensure your account has proper permissions and cloud saves."
                )

        return []

    def _extract_items_list(self, data: Any) -> list[dict[str, Any]]:
        """Extracts container/document list from JSON response."""
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]

        if isinstance(data, dict):
            for key in ["containers", "documents", "items", "data", "blobs"]:
                val = data.get(key)
                if isinstance(val, list):
                    return [x for x in val if isinstance(x, dict)]

        return []

    def _parse_world_item(self, index: int, item: dict[str, Any]) -> WorldInfo:
        """Transforms an API dictionary record into a WorldInfo instance."""
        world_id = str(
            item.get("fileName")
            or item.get("containerId")
            or item.get("name")
            or item.get("id")
            or f"world_{index}"
        )
        name = str(item.get("displayName") or item.get("name") or item.get("title") or world_id)

        # Parse modification date
        date_raw = (
            item.get("clientFileTime")
            or item.get("lastModified")
            or item.get("timestamp")
            or item.get("modifiedTime")
        )
        modified_at = None
        if date_raw:
            try:
                if isinstance(date_raw, str):
                    modified_at = datetime.fromisoformat(date_raw.replace("Z", "+00:00"))
                elif isinstance(date_raw, (int, float)):
                    modified_at = datetime.fromtimestamp(date_raw, tz=timezone.utc)
            except Exception:
                modified_at = None

        # Parse size in bytes
        size_raw = (
            item.get("size") or item.get("totalBytes") or item.get("sizeBytes") or item.get("bytes")
        )
        size_bytes = int(size_raw) if size_raw is not None else None

        container_name = item.get("fileName") or item.get("name") or item.get("containerId")

        return WorldInfo(
            index=index,
            world_id=world_id,
            name=name,
            modified_at=modified_at,
            size_bytes=size_bytes,
            thumbnail_available=False,
            container_name=container_name,
        )

    def get_world_manifest(self, world_id: str) -> dict[str, str]:
        """
        Fetches the JSON manifest of a world, containing its atom mapping.
        Returns a dictionary of {atom_name: blob_identifier}.
        """
        url = (
            f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({self.xuid})/"
            f"scids/{self.scid}/{world_id}"
        )
        resp = self.http_client.request("GET", url, headers=self._headers())

        if resp.status_code == 429:
            raise RateLimitError("Xbox Live Connected Storage rate limit reached (HTTP 429).")

        if resp.status_code in (401, 403):
            raise AccessDeniedError(
                f"Access denied to Connected Storage (HTTP {resp.status_code})."
            )

        if resp.status_code == 404:
            raise WorldNotFoundError(f"World '{world_id}' not found in the cloud.")

        if resp.is_error:
            raise NetworkError(
                f"Failed to fetch world manifest (HTTP {resp.status_code}): {resp.text}"
            )

        data = resp.json()
        atoms = data.get("atoms", {})
        if not isinstance(atoms, dict):
            raise NetworkError(f"Invalid manifest format for world '{world_id}'.")
        return atoms

    def download_atom(self, atom_path: str) -> bytes:
        """
        Downloads binary payload of an atom by identifier/path.
        Example: '5088CDC5-585A-42C4-AD9A-89A9892908BC,binary'
        """
        url = (
            f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({self.xuid})/"
            f"scids/{self.scid}/{atom_path}"
        )
        resp = self.http_client.request("GET", url, headers=self._headers())

        if resp.status_code == 429:
            raise RateLimitError("Xbox Live Connected Storage rate limit reached (HTTP 429).")

        if resp.status_code in (401, 403):
            raise AccessDeniedError(
                f"Access denied to Connected Storage (HTTP {resp.status_code})."
            )

        if resp.status_code == 404:
            raise NetworkError(f"Atom '{atom_path}' not found in the cloud.")

        if resp.is_error:
            raise NetworkError(
                f"Error downloading atom '{atom_path}' (HTTP {resp.status_code}): {resp.text}"
            )

        return resp.content

    def list_blobs(self, container_name: str) -> list[BlobRef]:
        """
        Lists files (blobs) inside a given container.
        Supports direct blobs endpoint as well as atom manifest fallback.
        """
        url = (
            f"{TITLE_STORAGE_BASE_URL}/connectedstorage/users/xuid({self.xuid})/"
            f"scids/{self.scid}/containers/{container_name}/blobs"
        )
        resp = self.http_client.request("GET", url, headers=self._headers())

        if resp.status_code == 404:
            # Fall back to atom manifest if direct blobs route returns 404
            try:
                atoms = self.get_world_manifest(container_name)
                return [
                    BlobRef(
                        container=container_name,
                        blob_name=atom_name,
                        size_bytes=None,
                        etag=None,
                        download_url=atom_id,
                    )
                    for atom_name, atom_id in atoms.items()
                ]
            except Exception:
                raise WorldNotFoundError(
                    f"Container '{container_name}' not found in the cloud."
                ) from None

        if resp.is_error:
            raise NetworkError(f"Failed to list world files (HTTP {resp.status_code}): {resp.text}")

        data = resp.json()
        raw_blobs = self._extract_items_list(data)

        blobs: list[BlobRef] = []
        for b in raw_blobs:
            blob_name = str(b.get("name") or b.get("blobName") or b.get("fileName", ""))
            size = b.get("size") or b.get("sizeBytes") or b.get("bytes")
            size_bytes = int(size) if size is not None else None
            etag = b.get("etag")
            download_url = b.get("url") or b.get("downloadUrl")

            blobs.append(
                BlobRef(
                    container=container_name,
                    blob_name=blob_name,
                    size_bytes=size_bytes,
                    etag=etag,
                    download_url=download_url,
                )
            )

        return blobs
