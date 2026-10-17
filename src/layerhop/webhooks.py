"""Webhook signature verification.

LayerHop signs every delivery with the ``LayerHop-Signature`` header::

    LayerHop-Signature: t=<unix seconds>,v1=<hex hmac_sha256(secret, "<t>.<raw body>")>

Always verify against the *raw* request body (bytes as received), before parsing JSON.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any, Dict, List, Optional, Union

from .errors import WebhookSignatureError

SIGNATURE_HEADER = "LayerHop-Signature"
DEFAULT_TOLERANCE_SECONDS = 300


def _as_bytes(v: Union[str, bytes]) -> bytes:
    return v.encode("utf-8") if isinstance(v, str) else v


def _parse_header(header: str) -> "tuple[Optional[int], List[str]]":
    t: Optional[int] = None
    sigs: List[str] = []
    for part in header.split(","):
        k, sep, v = part.strip().partition("=")
        if not sep:
            continue
        if k == "t":
            try:
                t = int(v)
            except ValueError:
                return None, []
        elif k == "v1":
            sigs.append(v.strip())
    return t, sigs


def compute_webhook_signature(secret: Union[str, bytes], timestamp: int, body: Union[str, bytes]) -> str:
    """Hex HMAC-SHA256 of ``"<timestamp>.<body>"`` -- useful for tests of your own endpoint."""
    msg = str(timestamp).encode("ascii") + b"." + _as_bytes(body)
    return hmac.new(_as_bytes(secret), msg, hashlib.sha256).hexdigest()


def verify_webhook_signature(
    secret: Union[str, bytes],
    body: Union[str, bytes],
    header: Optional[str],
    tolerance: int = DEFAULT_TOLERANCE_SECONDS,
    now: Optional[float] = None,
) -> bool:
    """Return True when ``header`` is a valid, fresh signature of ``body`` for ``secret``.

    Rejects timestamps more than ``tolerance`` seconds away from ``now`` (replay protection).
    Accepts any of several ``v1=`` values (secret rotation). Comparison is constant-time.
    """
    if not header:
        return False
    t, sigs = _parse_header(header)
    if t is None or not sigs:
        return False
    current = time.time() if now is None else now
    if abs(current - t) > tolerance:
        return False
    expected = compute_webhook_signature(secret, t, body)
    return any(hmac.compare_digest(expected, s) for s in sigs)


def construct_webhook_event(
    secret: Union[str, bytes],
    body: Union[str, bytes],
    header: Optional[str],
    tolerance: int = DEFAULT_TOLERANCE_SECONDS,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Verify the signature and return the parsed event, or raise :class:`WebhookSignatureError`."""
    if not verify_webhook_signature(secret, body, header, tolerance=tolerance, now=now):
        raise WebhookSignatureError("Invalid or expired LayerHop-Signature")
    return json.loads(_as_bytes(body))
