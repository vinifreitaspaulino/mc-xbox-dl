# Technical Decision Records — mc-xbox-dl

## S-001 — Adopted Assumptions
- **S1:** Minecraft Bedrock Connected Storage is accessible via an XSTS token obtained using a public `client_id` and the user owning the data.
- **S2:** Worlds are served as a collection of binary blobs that, upon reconstruction and optional gzip decompression, form a standard Bedrock world directory.
- **S3:** Only worlds actively synchronized to Xbox Live cloud storage appear (worlds stored strictly offline on local console disk are not in cloud storage).
- **S4:** Realms is out of scope (it is a separate paid service with distinct infrastructure).
- **S5:** Personal backup use of the unofficial API is permissible for own data porting; public documentation must include formal non-affiliation disclaimers and terms of service guidance.

---

## D-001 — Authentication Flow and Client ID Selection
- **Date:** 2026-10-15
- **Context:** Need to authenticate users against Microsoft accounts without password prompting (L3), without automated headless browsers (L6), without costs, and without requiring prior Azure application registration.
- **Decision:** Adopt the **OAuth 2.0 Device Code Flow** utilizing the public client ID of Minecraft Bedrock Android (`0000000048183522`) with scope `service::user.auth.xboxlive.com::MBI_SSL` at `login.live.com/oauth20_connect.srf`. Provide fallback via environment variable `MC_XBOX_DL_CLIENT_ID` in `config.py` should users desire a custom client ID.
- **Discarded Alternatives:**
  - *SISU flow with ECDSA P-256 for initial code:* Android client ID was simpler for initial MSA ticketing.
  - *Browser Automation / Selenium:* Violates L6 and requires heavy browser binaries.
- **Source/Evidence:** `gophertunnel/minecraft/auth`, `prismarine-auth`, Microsoft OAuth 2.0 Device Flow specification.
- **Status:** Confirmed.

---

## D-002 — Identification of TitleId and SCID for Minecraft Bedrock
- **Date:** 2026-10-15
- **Context:** Earlier drafts had discrepancies between SCID and TitleId constants.
- **Decision:** Define decimal TitleId as `1828326430` (`0x6CFA0C1E`) and primary Xbox console SCID as `00000000-0000-0000-0000-00006cfa0c1e`.
- **Source/Evidence:** Microsoft GDK documentation (*Troubleshooting Xbox Services network traffic for PC games*), public research tools.
- **Status:** Confirmed.

---

## D-003 — Output Package Format and Structural Validation
- **Date:** 2026-10-15
- **Context:** Exported worlds must import reliably with a double-click on Minecraft Bedrock Windows.
- **Decision:** Package as ZIP using `zipfile.ZIP_DEFLATED` with `.mcworld` extension, placing `level.dat`, `levelname.txt`, and `db/` directly at the root of the archive. Apply strict structural validation (valid Bedrock NBT header in `level.dat`, presence of `levelname.txt`, `db/CURRENT`, and manifest files) before atomically renaming temporary `.part` files.
- **Discarded Alternatives:**
  - *Root subdirectory within ZIP:* Rejected because Minecraft Bedrock fails to import `.mcworld` archives containing top-level folders.
- **Source/Evidence:** Mojang Bedrock `.mcworld` format specification.
- **Status:** Confirmed.

---

## D-004 — Handling Blob Compression (gzip)
- **Date:** 2026-10-15
- **Context:** Xbox Connected Storage can store individual world blobs compressed to minimize cloud data transfer.
- **Decision:** In the assembly layer (`packer/assemble.py`), inspect the initial magic bytes of each unpacked blob. If the gzip header (`0x1F 0x8B`) is detected, automatically decompress in memory before writing to disk.
- **Discarded Alternatives:**
  - *Assuming uncompressed raw bytes:* Causes world corruption when blobs are gzip-compressed by Xbox Live.
- **Source/Evidence:** Microsoft GDK (*XblConnectedStorage.exe* documentation).
- **Status:** Confirmed.

---

## D-005 — `response_type=device_code` Parameter in MSA OAuth Endpoint
- **Date:** 2026-10-15
- **Context:** When initiating Device Code requests against `https://login.live.com/oauth20_connect.srf`, Microsoft's endpoint returns HTTP 400 with `"unsupported_response_type"` unless `"device_code"` is explicitly specified instead of `"code"`.
- **Decision:** Specify `response_type: "device_code"` in payload calls to `oauth20_connect.srf`.
- **Source/Evidence:** Live `login.live.com` response validation.
- **Status:** Confirmed.

---

## D-006 — PoP Signatures (ECDSA P-256) and SISU Authorization
- **Date:** 2026-10-15
- **Context:** Standard User Tokens without title authentication are rejected by `titlestorage.xboxlive.com` with HTTP 403 `Reason: NoAccess` (code 2011). Connected Storage requires requests to be authenticated under a recognized Xbox ecosystem TitleId.
- **Decision:** Implement ephemeral ECDSA P-256 key pair generation (`cryptography`), perform device authentication against `device.auth.xboxlive.com/device/authenticate` with binary Proof-of-Possession (PoP) signature headers, and exchange for title-authorized XSTS tokens via `https://sisu.xboxlive.com/authorize` targeting TitleId `1828326430`.
- **Source/Evidence:** Live authorization testing yielding HTTP 200 responses on Connected Storage quota and container queries.
- **Status:** Confirmed.

---

## D-007 — Quota Verification and 404 (Code 2005) Handling
- **Date:** 2026-10-15
- **Context:** When an account has no synchronized cloud saves for the Minecraft SCID, storage endpoints respond with HTTP 404 and error `code: 2005 ("The requested data was not found")`.
- **Decision:** Gracefully interpret 404 responses with code 2005 or empty blob lists as an empty world collection (`[]`), presenting user-friendly guidance on ensuring console cloud synchronization.
- **Source/Evidence:** Live response from `titlestorage.xboxlive.com`.
- **Status:** Confirmed.

---

## D-008 — Package Family Name (PFN) Header Requirement
- **Date:** 2026-10-15
- **Context:** Access to console cloud saves on Connected Storage requires the package family name header matching the title edition.
- **Decision:** Include header `x-xbl-pfn: Microsoft.186805A1E9E_8wekyb3d8bbwe` on all Connected Storage queries.
- **Source/Evidence:** Live Connected Storage testing yielding HTTP 200 OK with full container listings.
- **Status:** Confirmed.

---

## D-009 — Atom Download Protocol and Parsing
- **Date:** 2026-10-15
- **Context:** In Xbox Live Connected Storage, each Minecraft world save is structured as a container whose manifest (`WORLD<id>,savedgame`) maps atom keys to GUIDs: `{"atoms": {"...": "<GUID>,binary"}}`.
- **Decision:** Retrieve atom mappings from the container manifest and fetch each binary atom from `/scids/{scid}/{atom_guid},binary`. Decode binary atom headers: 13-byte prefix, 1 byte path length $L$, $L$ bytes relative UTF-8 path, followed by raw payload bytes.
- **Source/Evidence:** Byte-level validation of Bedrock world chunks and LevelDB manifests.
- **Status:** Confirmed.

---

## D-010 — Filtering Cloud Synchronization Metadata Atoms
- **Date:** 2026-10-15
- **Context:** Cloud containers include internal synchronization tracking atoms such as `CLOUD_TIMESTAMP` and `CLOUD_WORLD_SAVE` with 0-byte payloads.
- **Decision:** Exclude any atom whose decoded relative path begins with `CLOUD_` from the generated `.mcworld` archive.
- **Source/Evidence:** Live world packaging and Bedrock import testing.
- **Status:** Confirmed.

---

## D-011 — Minecraft Bedrock to Java Edition Conversion via Chunker CLI
- **Date:** 2026-10-22
- **Context:** Bedrock worlds use LevelDB storage and custom NBT encoding incompatible with Minecraft Java Edition (Anvil region files and gzip NBT). Users wanting to play their Xbox worlds on Java Edition require format conversion without paid tools or third-party servers.
- **Decision:** Integrate the official open-source Chunker CLI (`HiveGamesOSS/Chunker`). Auto-download `chunker-cli-*.jar` from GitHub Releases into `%APPDATA%\mc-xbox-dl\bin\` with atomic write and caching. Require Java 17+ (validated via `java -version`), validate Java post-conversion structure (`level.dat` gzip magic bytes `0x1F 0x8B` and `region/`), support automatic installation into `.minecraft/saves` (Windows & Linux standard/Flatpak), and expand `ALLOWED_HOSTS` to support GitHub asset CDN redirection (`*.githubusercontent.com`).
- **Discarded Alternatives:**
  - *Third-party cloud conversion APIs:* Violates L1/L5/L10 (requires telemetry/third-party servers).
  - *Python-based LevelDB-to-Anvil converter:* High maintenance burden and potential data loss compared to the official Chunker engine maintained by HiveGames/Mojang partners.
- **Source/Evidence:** `HiveGamesOSS/Chunker` repository and successful conversion/validation on Java 17+.
- **Status:** Confirmed.


