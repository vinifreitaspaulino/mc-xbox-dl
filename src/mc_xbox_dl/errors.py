"""Domain exceptions and process exit code mappings."""


class McXboxDlError(Exception):
    """Base exception for all mc-xbox-dl application errors."""

    exit_code: int = 1

    def __init__(self, message: str, exit_code: int | None = None) -> None:
        super().__init__(message)
        if exit_code is not None:
            self.exit_code = exit_code


class UsageError(McXboxDlError):
    """Usage error or invalid command-line arguments."""

    exit_code = 2


class NotAuthenticatedError(McXboxDlError):
    """Session not found, expired, or invalid."""

    exit_code = 3


class NetworkError(McXboxDlError):
    """Network connection error or remote service unavailable."""

    exit_code = 4


class WorldNotFoundError(McXboxDlError):
    """Specified world was not found or world list is empty."""

    exit_code = 5


class PackagingError(McXboxDlError):
    """Failure during world assembly, validation, or .mcworld packaging."""

    exit_code = 6


class AccessDeniedError(McXboxDlError):
    """Access denied, insufficient permissions, or XSTS authorization failure."""

    exit_code = 7


class RateLimitError(McXboxDlError):
    """API rate limit encountered (HTTP 429)."""

    exit_code = 8


class ConversionError(McXboxDlError):
    """Failure during Java runtime check, Chunker download, or Bedrock-to-Java conversion."""

    exit_code = 9
