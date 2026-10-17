# Security Policy

## Overview
`mc-xbox-dl` is an open-source, local-first Command-Line Interface (CLI) utility designed to help users export and back up their own personal Minecraft Bedrock world saves synchronized to Xbox Live cloud storage.

Security and user privacy are foundational design principles of this project.

---

## Security Model

### 1. Strictly Local Execution
- All network communication occurs exclusively between the user's local machine and official Microsoft/Xbox Live endpoints.
- No third-party servers, relays, analytical proxies, or external telemetry collectors are contacted.
- No user tokens, credentials, or world contents are ever transmitted to the project maintainers or any other remote service.

### 2. Credential Storage & Token Masking
- Authentication uses Microsoft's **OAuth 2.0 Device Code Flow**. Users enter a temporary code directly into official Microsoft verification portals (`https://www.microsoft.com/link` or `https://aka.ms/remoteconnect`).
- User passwords are never requested, handled, or stored by the CLI.
- Persistent session tokens (`session.json`) are stored locally in the operating system's designated user configuration folder (`%APPDATA%\mc-xbox-dl` on Windows).
- On Windows systems, file access control lists (ACLs) are configured to restrict read and write permissions strictly to the executing user account.
- Diagnostic logs and debug dumps generated via `--debug` automatically redact sensitive fields (such as refresh tokens, access tokens, XSTS tokens, and authorization headers).

### 3. Read-Only (GET) Cloud Interaction
- The tool operates in strict **read-only** mode against Xbox Live Connected Storage and Title Storage APIs.
- The tool only executes HTTP `GET` requests against cloud storage. It does not perform `PUT`, `POST`, or `DELETE` requests to cloud save data, preventing accidental corruption or deletion of remote worlds.

### 4. Rate Limiting and Fail-Fast Protection
- To minimize unexpected account throttling or security alerts from Xbox Live edge firewalls:
  - Batch downloads apply rate pacing (temporal spacing) between consecutive world transfers.
  - Short-lived local caching is used to avoid duplicate queries to Title Storage endpoints.
  - A neutral HTTP client `User-Agent` is utilized across requests.
  - Any HTTP `401` (Unauthorized), `403` (Forbidden), or `429` (Rate Limited) response triggers an immediate, safe abort of batch operations to protect the user's account from repeated failed requests.

### 5. Path Traversal & Sandbox Safeguards
- World atom unpacking and file extraction employ strict path normalization checks to prevent directory traversal attacks (e.g., preventing relative paths such as `../` from escaping target directories).
- Reserved Windows file and device names (such as `CON`, `PRN`, `AUX`, `NUL`) are sanitized prior to disk writes.

---

## Reporting a Security Concern
If you discover a security issue or vulnerability in `mc-xbox-dl`, please do not open a public issue on GitHub. Instead, report it privately via GitHub Security Advisories or by contacting the maintainer directly.

