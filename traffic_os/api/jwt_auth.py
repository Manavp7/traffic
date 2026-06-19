"""Minimal HMAC-SHA256 JWT (no external dependency) layered over the RBAC roles."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def create_token(payload: dict, secret: str, *, exp_s: int = 3600) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    body = {**payload, "exp": int(time.time()) + exp_s, "iat": int(time.time())}
    seg = _b64url(json.dumps(header).encode()) + "." + _b64url(json.dumps(body).encode())
    sig = hmac.new(secret.encode(), seg.encode(), hashlib.sha256).digest()
    return seg + "." + _b64url(sig)


def verify_token(token: str, secret: str) -> dict | None:
    try:
        seg, sig = token.rsplit(".", 1)
        expected = hmac.new(secret.encode(), seg.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url_decode(sig), expected):
            return None
        payload = json.loads(_b64url_decode(seg.split(".", 1)[1]))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None
