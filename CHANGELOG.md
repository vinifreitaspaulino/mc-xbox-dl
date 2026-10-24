# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-10-22

### Added
- **Minecraft Java Edition Conversion (`--java`, `--java-version`, `--install-java`, `--java-saves-dir`):**
  - Integrated official open-source [Chunker CLI](https://github.com/HiveGamesOSS/Chunker) (`HiveGamesOSS/Chunker`) for Bedrock-to-Java world conversion.
  - Automatic download, progress display, and caching of `chunker-cli.jar` in `DATA_DIR / "bin"`.
  - Java runtime validation (`java -version`) ensuring Java 17+ requirement before starting conversions.
  - User-friendly target Java version parsing (e.g. `1.21.4`, `1.20.1`, `JAVA_1_21_4`).
  - Automatic detection and installation into `.minecraft/saves` for both Windows (`%APPDATA%\.minecraft\saves`) and Linux (native `~/.minecraft/saves` and Flatpak paths).
  - Structural validation of converted Java worlds (`level.dat` gzip magic bytes `0x1F 0x8B` and `region/` directory).
  - New domain exception `ConversionError` with exit code `9`.
  - Added support for safe HTTP redirects across GitHub Releases and GitHub CDN assets (`*.githubusercontent.com`).

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
