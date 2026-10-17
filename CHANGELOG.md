# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-10-16 — Initial Release

### Added
- **OAuth 2.0 & SISU Authentication (`login`, `logout`, `whoami`):**
  - Passwordless Microsoft Device Code authentication (`login.live.com`) with interactive consent gate and `--accept-risk` automation flag.
  - Ephemeral ECDSA P-256 Proof-of-Possession (PoP) request signing and SISU authorization to acquire title-scoped Xbox Live XSTS tokens (`TitleId 1828326430`).
  - Automatic silent token refresh and atomic local session storage (`session.json`).
- **Cloud World Listing & Caching (`list`):**
  - Read-only querying of Xbox Live Connected Storage (`titlestorage.xboxlive.com`) displaying world index, name, modification timestamp, and size via Rich tables.
  - 5-minute local listing cache (`cache.json`) with `--no-cache` bypass flag.
- **World Download & Packaging (`download`):**
  - Single-world download by index, world name, or cloud ID, and batch export (`--all`) with automatic resume and inter-world rate pacing.
  - Binary atom unpacking with path traversal defense, automatic in-memory `gzip` decompression (`0x1f 0x8b`), and filtering of internal `CLOUD_*` metadata markers.
  - Structural integrity validation of Bedrock NBT headers (`level.dat`), `levelname.txt`, and LevelDB files (`db/CURRENT`, `db/MANIFEST-*`) before atomic `.mcworld` ZIP creation.
- **Direct Local Installation (`--install`, `--install-dir`):**
  - Auto-discovery of modern Windows GDK (`%APPDATA%\Minecraft Bedrock\Users\<ID>\...`) and legacy UWP (`%LOCALAPPDATA%\Packages\Microsoft.MinecraftUWP_...\...`) world directories, with interactive multi-profile selection.
  - Cross-platform Linux compatibility with informative guidance for `mcpelauncher` world paths.
- **Internationalization & Diagnostics:**
  - Full bilingual CLI support (`en-US` and `pt-BR`) with automatic OS locale detection and persistent `--lang` preference.
  - Redacted `--debug` diagnostic dumps stripping all tokens, headers, and secrets.
