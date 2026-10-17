"""Data models for cloud storage (Connected Storage)."""

from dataclasses import dataclass
from datetime import datetime

from mc_xbox_dl.i18n import get_language, t


@dataclass(frozen=True)
class WorldInfo:
    """Summary of a cloud-saved world for display and selection."""

    index: int
    world_id: str
    name: str
    modified_at: datetime | None
    size_bytes: int | None
    thumbnail_available: bool = False
    container_name: str | None = None

    def formatted_size(self) -> str:
        """Returns the formatted size in B, KB, MB, or GB with localized decimal separator."""
        if self.size_bytes is None:
            return t("unknown")
        size = float(self.size_bytes)
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024.0 or unit == "GB":
                formatted = f"{size:.1f} {unit}"
                if get_language() == "pt":
                    formatted = formatted.replace(".", ",")
                return formatted
            size /= 1024.0
        return f"{self.size_bytes} B"

    def formatted_date(self) -> str:
        """Returns the formatted modification date."""
        if not self.modified_at:
            return t("unknown")
        return self.modified_at.strftime("%Y-%m-%d %H:%M")


@dataclass(frozen=True)
class BlobRef:
    """Reference to an individual file (blob) inside a cloud container."""

    container: str
    blob_name: str
    size_bytes: int | None = None
    etag: str | None = None
    download_url: str | None = None
