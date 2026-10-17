# Communication Protocol — mc-xbox-dl

This document specifies the exact sequence of HTTP requests, authentication flows, headers, payloads, binary data formats, and filesystem reconstruction rules used to communicate with Xbox Live and Connected Storage services for Minecraft Bedrock.

---

## 1. Authentication Architecture

The client authenticates using a multi-step OAuth 2.0 and Xbox Secure Token Service (XSTS / SISU) handshake.

```
+-------------------+      +--------------------+      +----------------------+
|  1. Device Code   | ---> |  2. Token Polling  | ---> |  3. Device Token     |
|     (MSA OAuth)   |      |  (Access/Refresh)  |      |   (ECDSA P-256 XBL)  |
+-------------------+      +--------------------+      +----------------------+
                                                                  |
                                                                  v
+-------------------+      +--------------------+      +----------------------+
|  6. Connected     | <--- |  5. Save Session   | <--- |  4. SISU / XSTS      |
|     Storage       |      |    (session.json)  |      |   Authorization      |
+-------------------+      +--------------------+      +----------------------+
```

### 1.1 Initiate Device Code Flow (Microsoft Account)
- **Method & URL:** `POST https://login.live.com/oauth20_connect.srf`
- **Headers:**
  - `Content-Type: application/x-www-form-urlencoded`
  - `User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36`
- **Body:**
  ```
  client_id=0000000048183522&scope=service::user.auth.xboxlive.com::MBI_SSL&response_type=code
  ```
- **Success Response (HTTP 200 JSON):**
  ```json
  {
    "user_code": "ABC12345",
    "device_code": "<opaque_device_code>",
    "verification_uri": "https://www.microsoft.com/link",
    "expires_in": 900,
    "interval": 5
  }
  ```
- **CLI Behavior:** Display `https://www.microsoft.com/link` (or `https://aka.ms/remoteconnect`) and `user_code` for the user to complete verification on their phone or PC browser.

---

### 1.2 Poll for MSA Token
- **Method & URL:** `POST https://login.live.com/oauth20_token.srf`
- **Headers:**
  - `Content-Type: application/x-www-form-urlencoded`
- **Body:**
  ```
  client_id=0000000048183522&grant_type=urn:ietf:params:oauth:grant-type:device_code&device_code=<device_code>
  ```
- **Response Handling:**
  - `HTTP 400` with `error: "authorization_pending"`: Wait for `interval` seconds (default 5s) and retry.
  - `HTTP 400` with `error: "slow_down"`: Increase polling interval by 5 seconds and continue polling.
  - `HTTP 400` with `error: "expired_token"`: Abort; device code expired.
  - `HTTP 400` with `error: "access_denied"`: Abort; user rejected authorization.
  - `HTTP 200` (Success):
    ```json
    {
      "token_type": "bearer",
      "expires_in": 86400,
      "scope": "service::user.auth.xboxlive.com::MBI_SSL",
      "access_token": "<msa_access_token>",
      "refresh_token": "<msa_refresh_token>",
      "user_id": "<user_id>"
    }
    ```

---

### 1.3 Refresh Token Flow
- **Method & URL:** `POST https://login.live.com/oauth20_token.srf`
- **Headers:**
  - `Content-Type: application/x-www-form-urlencoded`
- **Body:**
  ```
  client_id=0000000048183522&grant_type=refresh_token&refresh_token=<msa_refresh_token>&scope=service::user.auth.xboxlive.com::MBI_SSL
  ```
- **Response Handling:** An `invalid_grant` error indicates revoked credentials; delete local session and prompt for fresh login.

---

### 1.4 Device Authentication (ECDSA P-256)
Minecraft Bedrock client credentials require an Xbox device token generated via an ephemeral ECDSA P-256 keypair:
- **Method & URL:** `POST https://device.auth.xboxlive.com/device/authenticate`
- **Headers:**
  - `Content-Type: application/json`
  - `x-xbl-contract-version: 1`
- **Body (JSON):**
  ```json
  {
    "Properties": {
      "AuthMethod": "ProofOfPossession",
      "Id": "...",
      "DeviceType": "Android",
      "Version": "10",
      "ProofKey": {
        "crv": "P-256",
        "alg": "ES256",
        "use": "sig",
        "kty": "EC",
        "x": "<base64url_x>",
        "y": "<base64url_y>"
      }
    },
    "RelyingParty": "http://auth.xboxlive.com",
    "TokenType": "JWT"
  }
  ```
- **Success Response (HTTP 200 JSON):** Contains `Token` (`<device_token>`).

---

### 1.5 SISU Authorization (XSTS + User Hash)
- **Method & URL:** `POST https://sisu.xboxlive.com/authorize`
- **Headers:**
  - `Content-Type: application/json`
  - `x-xbl-contract-version: 1`
  - `Signature: <ecdsa_p256_pop_signature>`
- **Body (JSON):**
  ```json
  {
    "AccessToken": "t=<msa_access_token>",
    "AppId": "0000000048183522",
    "DeviceToken": "<device_token>",
    "Sandbox": "RETAIL",
    "SiteIdentity": "user.auth.xboxlive.com",
    "UseModernGamertag": true
  }
  ```
- **Success Response (HTTP 200 JSON):**
  Extract `AuthorizationToken.Token` (`<xsts_token>`), `DisplayClaims.xui[0].uhs` (`<user_hash>`), `DisplayClaims.xui[0].xid` (`<xuid>`), and `DisplayClaims.xui[0].gtg` (`<gamertag>`).

- **Known Xbox Live Error Codes (HTTP 401):**
  - `XErr: 2148916233`: Microsoft Account does not have an active Xbox Live profile.
  - `XErr: 2148916235`: Account is suspended/banned from Xbox Live.
  - `XErr: 2148916238`: Minor child account requires parental consent in Microsoft Family Safety.

---

## 2. Connected Storage (Xbox Cloud Storage)

### 2.1 Service Configuration & Identifiers
- **Minecraft TitleId:** `1828326430` (hexadecimal `6CFA0C1E`, Package `Microsoft.MinecraftUWPConsole`)
- **Service Configuration ID (SCID):** `00000000-0000-0000-0000-00006cfa0c1e`
- **Package Family Name (PFN):** `Microsoft.186805A1E9E_8wekyb3d8bbwe` (supplied via `x-xbl-pfn` header)

### 2.2 Standard Request Headers
All requests sent to `https://titlestorage.xboxlive.com` require:
```http
Authorization: XBL3.0 x=<user_hash>;<xsts_token>
x-xbl-contract-version: 1
x-xbl-pfn: Microsoft.186805A1E9E_8wekyb3d8bbwe
Accept: application/json, */*
```

---

### 2.3 List Cloud Worlds
- **Method & URL:** `GET https://titlestorage.xboxlive.com/connectedstorage/users/xuid({xuid})/scids/00000000-0000-0000-0000-00006cfa0c1e`
- **Success Response (HTTP 200 JSON):**
  ```json
  {
    "blobs": [
      {
        "fileName": "WORLDKzY4MVpUNUthZ0E9,savedgame",
        "displayName": "My Survival World",
        "size": 312028,
        "clientFileTime": "2026-04-01T02:25:26.5740000Z",
        "etag": "\"0x8DE8F96B975A6AA\""
      },
      {
        "fileName": "SETTINGS,savedgame",
        "displayName": "SETTINGS",
        "size": 1024,
        "clientFileTime": "2026-04-01T02:20:00.0000000Z"
      }
    ],
    "pagingInfo": {
      "totalItems": 2
    }
  }
  ```
- **Filtering Rules:**
  - Only entries whose `fileName` starts with `WORLD` are playable Minecraft saves.
  - Non-world entries like `SETTINGS,savedgame` are filtered out.
- **Local Caching:** Responses are cached locally for 300 seconds (5 minutes) to prevent redundant upstream queries. Use `--no-cache` to force immediate cloud retrieval.

---

### 2.4 World Manifest Query (Atom Map)
- **Method & URL:** `GET https://titlestorage.xboxlive.com/connectedstorage/users/xuid({xuid})/scids/{scid}/{fileName}`
  - Example: `GET .../scids/00000000-0000-0000-0000-00006cfa0c1e/WORLDKzY4MVpUNUthZ0E9,savedgame`
- **Success Response (HTTP 200 JSON):**
  ```json
  {
    "atoms": {
      "EMBEDDED_0f1e49c16f05091daf8dbb8d59114455c30efeba": "5088CDC5-585A-42C4-AD9A-89A9892908BC,binary",
      "EMBEDDED_78ff2cfa08b84c88aee5ca661960dfa2": "78FF2CFA-08B8-4C88-AEE5-CA661960DFA2,binary"
    }
  }
  ```

---

### 2.5 Binary Atom Download & Parsing
- **Method & URL:** `GET https://titlestorage.xboxlive.com/connectedstorage/users/xuid({xuid})/scids/{scid}/{atom_id}`
  - Example: `GET .../scids/00000000-0000-0000-0000-00006cfa0c1e/78FF2CFA-08B8-4C88-AEE5-CA661960DFA2,binary`
- **Binary Wire Layout:**
  - **Bytes `0..12` (13 bytes):** Magic header prefix (`\x00\x02\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00`).
  - **Byte `13` (1 byte):** Unsigned 8-bit integer $L$ representing the relative file path length.
  - **Bytes `14 .. 14+L` ($L$ bytes):** Relative file path string encoded in UTF-8 (e.g., `level.dat`, `levelname.txt`, `db/000052.log`).
  - **Bytes `14+L .. EOF`:** Raw uncompressed binary contents of the target file.
- **Metadata Markers:** Atoms named `CLOUD_TIMESTAMP` or `CLOUD_WORLD_SAVE` are internal cloud synchronization markers containing zero-length or synchronization metadata; they are safely skipped during world reconstruction.

---

## 3. World Assembly & Packaging (`.mcworld`)

The reconstructed world directory is validated and packed into a standard `.mcworld` file (which is a standard ZIP archive with files stored directly at the root):

```
level.dat                 # World metadata and player state (Bedrock NBT format)
level.dat_old             # Previous state backup (optional)
levelname.txt             # Human-readable world name displayed in the menu
world_icon.jpeg           # World thumbnail image (optional)
world_behavior_packs.json # Behavior pack bindings (optional)
world_resource_packs.json # Resource pack bindings (optional)
db/                       # LevelDB world storage database
  CURRENT
  MANIFEST-000000
  *.log
  *.ldb
```

### 3.1 Post-Assembly Integrity Checks
Before finalizing any archive or installing files:
1. `level.dat`, `levelname.txt`, and the `db/` folder must exist.
2. `db/CURRENT` and at least one `db/MANIFEST-*` file must be present.
3. The 8-byte Bedrock header of `level.dat` is checked (little-endian unsigned 32-bit version number + 32-bit payload length).
4. **Atomic Write Guarantee:** The archive is assembled into a temporary `.part` file and atomically renamed (`os.replace`) upon passing all validation checks.

---

## 4. Rate Limiting and Safety Controls

1. **Inter-World Delay Pacing:** During batch downloads (`--all`), the client waits 1.5 seconds between consecutive worlds to avoid triggering Xbox Live edge firewalls.
2. **Fail-Fast Safety Abort:** If Xbox Live returns HTTP `429` (Rate Limited) or HTTP `401/403` (Authentication/Authorization Failure), batch execution halts immediately to safeguard the user's account against automated policy restrictions.

