"""Cryptography and Proof-of-Possession (PoP) digital signature generation for Xbox Live."""

import base64
import struct
import time
import urllib.parse

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature


def generate_keypair() -> ec.EllipticCurvePrivateKey:
    """Generates an ECDSA P-256 (SECP256R1) keypair for PoP request signing."""
    return ec.generate_private_key(ec.SECP256R1())


def export_proof_key(private_key: ec.EllipticCurvePrivateKey) -> dict[str, str]:
    """
    Exports public key in the JWK format required by Xbox Live APIs.
    Fields: use, alg, kty, crv, x, y.
    """
    public_numbers = private_key.public_key().public_numbers()
    x_b64 = base64.urlsafe_b64encode(public_numbers.x.to_bytes(32, "big")).decode().rstrip("=")
    y_b64 = base64.urlsafe_b64encode(public_numbers.y.to_bytes(32, "big")).decode().rstrip("=")
    return {
        "use": "sig",
        "alg": "ES256",
        "kty": "EC",
        "crv": "P-256",
        "x": x_b64,
        "y": y_b64,
    }


def compute_signature(
    url: str,
    method: str,
    body: str | bytes,
    private_key: ec.EllipticCurvePrivateKey,
    auth_token: str = "",
    custom_timestamp: int | None = None,
) -> str:
    """
    Computes binary Proof-of-Possession (PoP) signature for 'Signature' HTTP headers.

    Signed buffer layout:
      uint32(1) (signature version, big-endian)
      0x00
      uint64(windows_filetime_ticks, big-endian)
      0x00
      ASCII(method.upper())
      0x00
      ASCII(path_and_query)
      0x00
      ASCII(auth_token)
      0x00
      body_bytes
      0x00

    Signature header return value:
      base64( uint32(1) + uint64(windows_ticks) + raw_sig_p1363 (64 bytes) )
    """
    if custom_timestamp is not None:
        windows_ts = custom_timestamp
    else:
        # Windows FileTime ticks = (unix_timestamp + 11644473600) * 10_000_000
        windows_ts = (int(time.time()) + 11644473600) * 10000000

    parsed = urllib.parse.urlparse(url)
    path_and_query = parsed.path
    if parsed.query:
        path_and_query = f"{path_and_query}?{parsed.query}"

    body_bytes = body.encode("utf-8") if isinstance(body, str) else body

    buf = bytearray()
    buf.extend(struct.pack(">I", 1))
    buf.append(0)
    buf.extend(struct.pack(">Q", windows_ts))
    buf.append(0)
    buf.extend(method.upper().encode("ascii"))
    buf.append(0)
    buf.extend(path_and_query.encode("utf-8"))
    buf.append(0)
    buf.extend(auth_token.encode("utf-8"))
    buf.append(0)
    buf.extend(body_bytes)
    buf.append(0)

    sig_der = private_key.sign(bytes(buf), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(sig_der)
    sig_p1363 = r.to_bytes(32, "big") + s.to_bytes(32, "big")

    header_buf = bytearray()
    header_buf.extend(struct.pack(">I", 1))
    header_buf.extend(struct.pack(">Q", windows_ts))
    header_buf.extend(sig_p1363)

    return base64.b64encode(header_buf).decode("ascii")
