"""Encrypt small secrets at rest (the Blackboard feed URL). Standard library only, no new dependencies.

Production: set env KMS_KEY_ID (key id, ARN or alias). `seal` then calls KMS Encrypt directly (a feed URL is at most
2,000 bytes, well under the 4,096 byte KMS limit, so no data key or AES library is needed). The encryption
context binds the ciphertext to its purpose and its owner, so a ciphertext copied into another user's item
cannot be decrypted. Ciphertext format: "kms1:" + base64.

Development fallback (KMS_KEY_ID not set): "dev1:" + base64 of nonce|ciphertext|tag, built from HMAC-SHA256 in counter
mode with a key from env DEV_SECRETBOX_KEY (or a built-in constant). THIS IS NOT SECURE STORAGE, it only keeps the URL
from sitting in the table as readable text during local work and tests. Set REQUIRE_KMS=1 in deployed environments
and `seal` refuses to use the fallback (and `open` refuses dev ciphertext).

Nothing here logs or returns plaintext; errors carry no secret material.
"""
import base64
import hashlib
import hmac
import os
import secrets

_DEV_DEFAULT_KEY = b"semesteros-DEV-ONLY-not-a-secret"
_kms_client = None


class SecretBoxError(Exception):
    pass


def set_kms_client(client) -> None:
    """Tests inject a fake with encrypt(**kw) and decrypt(**kw)."""
    global _kms_client
    _kms_client = client


def _kms():
    global _kms_client
    if _kms_client is None:
        import boto3  # late import: tests and the dev path need no AWS libraries
        _kms_client = boto3.client("kms", region_name=os.environ.get("REGION", "us-east-1"))
    return _kms_client


def mode() -> str:
    """'kms' when a key id is configured, else 'dev'."""
    return "kms" if os.environ.get("KMS_KEY_ID", "").strip() else "dev"


def _context(purpose: str, sub: str) -> dict:
    return {"purpose": str(purpose)[:40], "sub": str(sub)[:128]}


def _dev_key() -> bytes:
    return os.environ.get("DEV_SECRETBOX_KEY", "").encode() or _DEV_DEFAULT_KEY


def _stream(key: bytes, nonce: bytes, n: int) -> bytes:
    out, counter = b"", 0
    while len(out) < n:
        out += hmac.new(key, b"enc" + nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        counter += 1
    return out[:n]


def _dev_seal(plain: bytes, purpose: str, sub: str) -> str:
    key, nonce = _dev_key(), secrets.token_bytes(16)
    ct = bytes(a ^ b for a, b in zip(plain, _stream(key, nonce, len(plain))))
    tag = hmac.new(key, b"mac" + nonce + ct + repr(_context(purpose, sub)).encode(), hashlib.sha256).digest()
    return "dev1:" + base64.b64encode(nonce + ct + tag).decode()


def _dev_open(blob: str, purpose: str, sub: str) -> bytes:
    try:
        raw = base64.b64decode(blob, validate=True)
        nonce, ct, tag = raw[:16], raw[16:-32], raw[-32:]
    except Exception:
        raise SecretBoxError("bad ciphertext")
    key = _dev_key()
    want = hmac.new(key, b"mac" + nonce + ct + repr(_context(purpose, sub)).encode(), hashlib.sha256).digest()
    if len(raw) < 48 or not hmac.compare_digest(tag, want):
        raise SecretBoxError("bad ciphertext")
    return bytes(a ^ b for a, b in zip(ct, _stream(key, nonce, len(ct))))


def seal(plaintext: str, purpose: str, sub: str) -> str:
    """Encrypt `plaintext` for (purpose, sub). Returns a printable string safe to store."""
    data = plaintext.encode("utf-8")
    key_id = os.environ.get("KMS_KEY_ID", "").strip()
    if key_id:
        try:
            resp = _kms().encrypt(KeyId=key_id, Plaintext=data, EncryptionContext=_context(purpose, sub))
            return "kms1:" + base64.b64encode(resp["CiphertextBlob"]).decode()
        except Exception:
            raise SecretBoxError("encryption unavailable")
    if os.environ.get("REQUIRE_KMS", "").strip().lower() in ("1", "true", "yes"):
        raise SecretBoxError("encryption unavailable")
    return _dev_seal(data, purpose, sub)


def open_(blob: str, purpose: str, sub: str) -> str:
    """Decrypt a value made by `seal` for the same (purpose, sub). Raises SecretBoxError on any problem."""
    if not isinstance(blob, str):
        raise SecretBoxError("bad ciphertext")
    if blob.startswith("kms1:"):
        try:
            raw = base64.b64decode(blob[5:], validate=True)
            resp = _kms().decrypt(CiphertextBlob=raw, EncryptionContext=_context(purpose, sub))
            return resp["Plaintext"].decode("utf-8")
        except Exception:
            raise SecretBoxError("decryption failed")
    if blob.startswith("dev1:"):
        if os.environ.get("REQUIRE_KMS", "").strip().lower() in ("1", "true", "yes"):
            raise SecretBoxError("decryption failed")
        return _dev_open(blob[5:], purpose, sub).decode("utf-8", "replace")
    raise SecretBoxError("bad ciphertext")
