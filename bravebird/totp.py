from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import time


def _base32_to_bytes(secret: str) -> bytes:
    padding = "=" * (-len(secret) % 8)
    return base64.b32decode(secret.upper().replace(" ", "") + padding)


def generate_totp(secret: str, timestamp: int | None = None, digits: int = 6, step_seconds: int = 30) -> str:
    if timestamp is None:
        timestamp = int(time.time() * 1000)
    counter = timestamp // 1000 // step_seconds
    counter_bytes = counter.to_bytes(8, "big")
    digest = hmac.new(_base32_to_bytes(secret), counter_bytes, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (
        ((digest[offset] & 0x7F) << 24)
        | ((digest[offset + 1] & 0xFF) << 16)
        | ((digest[offset + 2] & 0xFF) << 8)
        | (digest[offset + 3] & 0xFF)
    )
    return str(code % (10**digits)).zfill(digits)


async def get_code(_challenge: str | None, secret: str) -> str:
    return generate_totp(secret)
