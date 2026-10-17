# Protocol Research — mc-xbox-dl

## 1. Technical Feasibility
**Feasible with considerations.**
Technical feasibility is evidenced by community interoperability utilities and Microsoft GDK Connected Storage specifications performing cloud save synchronization via Microsoft Device Authorization (`aka.ms/remoteconnect`) and Xbox cloud storage. Authentication APIs (OAuth 2.0 Device Code, User Tokens, and Title XSTS) and the Connected Storage architecture (`titlestorage.xboxlive.com`) are documented in the Microsoft GDK and verified in reputable open-source projects (`gophertunnel`, `prismarine-auth`, `XblContainerReader`).

## 2. Referenced Open-Source Projects and Documentation
| # | URL / Reference | Language | License | Activity | Usage / Insight |
|---|---|---|---|---|---|
| 1 | `https://github.com/sandertv/gophertunnel` | Go | Apache 2.0 | Active | Public Minecraft Bedrock client IDs (`0000000048183522` Android, `000000004c17c01a` iOS), `login.live.com` (MBI_SSL) endpoints, and decimal TitleId mappings. |
| 2 | `https://github.com/PrismarineJS/prismarine-auth` | JavaScript | MIT | Active | Live and SISU token exchange flows, User Token to XSTS token exchange targeting `http://xboxlive.com`, and `XErr` error code mappings. |
| 3 | `https://github.com/OpenXbox/xbox-webapi-python` | Python | MIT | Active | Xbox Live request structure, `Authorization: XBL3.0 x=<uhs>;<xsts>` headers, session representations, and claim parsing. |
| 4 | Microsoft GDK Documentation: *Troubleshooting Xbox Services traffic* & *Game Saves tools* | Official Documentation | N/A | Current | Connected Storage endpoints at `titlestorage.xboxlive.com/connectedstorage/users/xuid(...)/scids/...`, SCID formatting, and container/blob layouts. |
| 5 | Public Tools & Save Extractors (`XblContainerReader`, `XGP-save-extractor`) | C# / Python | MIT | Active | Windows Game Save (WGS / Connected Storage) container models, blob offsets, and gzip compression inspection. |

## 3. Authentication Architecture
- **Primary Flow:** OAuth 2.0 Device Code Flow via `login.live.com` (scope `service::user.auth.xboxlive.com::MBI_SSL`).
- **Public Client ID:** `0000000048183522` (Minecraft Bedrock Android).
  - *Purpose:* Standard client ID in the Minecraft open-source ecosystem (`gophertunnel`, `bedrock-protocol`) for authenticating Bedrock players without requiring private enterprise secret registrations.
  - *User Verification URL:* `https://www.microsoft.com/link` or `https://aka.ms/remoteconnect`.
- **Title Authentication (SISU / ECDSA):**
  - Title authorization via `https://sisu.xboxlive.com/authorize` with ephemeral ECDSA P-256 device signatures is used to acquire title-scoped XSTS tokens for TitleId `1828326430`.

## 4. Connected Storage Architecture
- **Minecraft Bedrock Xbox Constants:**
  - **TitleId:** `1828326430` (`0x6CFA0C1E`).
  - **SCID:** `00000000-0000-0000-0000-00006cfa0c1e`.
  - **Package Family Name (PFN):** `Microsoft.186805A1E9E_8wekyb3d8bbwe`.
- **Key Endpoints:**
  - Container listing: `GET /connectedstorage/users/xuid({xuid})/scids/{scid}`
  - Container manifest: `GET /connectedstorage/users/xuid({xuid})/scids/{scid}/{container_id}`
  - Binary atom download: `GET /connectedstorage/users/xuid({xuid})/scids/{scid}/{atom_id},binary`
- **Headers:**
  - `Authorization: XBL3.0 x=<user_hash>;<xsts_token>`
  - `x-xbl-contract-version: 1`
  - `x-xbl-pfn: Microsoft.186805A1E9E_8wekyb3d8bbwe`
  - `Accept: application/json, */*`

## 5. Data Representation & Extraction
- **Containers and Blobs:**
  - Each Bedrock world is stored as an Xbox cloud container containing a collection of binary atoms.
  - Unpacked atoms reconstruct essential world elements: `level.dat`, `levelname.txt`, and LevelDB chunk databases (`db/CURRENT`, `db/MANIFEST-...`, `db/*.ldb`, `db/*.log`).
- **Gzip Decompression:**
  - Individual blobs may be gzip-compressed by Xbox Live; decompress in-memory when magic bytes `0x1F 0x8B` are encountered.
- **Exclusions:**
  - Cloud metadata records (`CLOUD_TIMESTAMP`, `CLOUD_WORLD_SAVE`) are excluded from output `.mcworld` archives.

## 6. Safety and Legal Considerations
- **Read-Only Operation:** The tool issues only read (GET) requests, avoiding cloud save modifications or state corruptions.
- **Local Credentials:** No credentials or tokens leave the local machine. Sensitive tokens are masked in logs and debug dumps.
- **Independent & Unofficial:** The utility is not affiliated with or endorsed by Microsoft or Mojang Studios.

