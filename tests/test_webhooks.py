import hashlib
import hmac
import json

import pytest

from layerhop import WebhookSignatureError, compute_webhook_signature, construct_webhook_event, verify_webhook_signature

SECRET = "whsec_test"
BODY = json.dumps({"id": "evt_1", "type": "order.filled", "createdAt": "2026-10-17T00:00:00Z", "data": {"order": {}}})
T = 1760000000


def sign(body=BODY, t=T, secret=SECRET):
    return hmac.new(secret.encode(), f"{t}.{body}".encode(), hashlib.sha256).hexdigest()


def test_valid_signature_str_and_bytes():
    h = f"t={T},v1={sign()}"
    assert verify_webhook_signature(SECRET, BODY, h, now=T)
    assert verify_webhook_signature(SECRET.encode(), BODY.encode(), h, now=T + 299)
    assert compute_webhook_signature(SECRET, T, BODY) == sign()


def test_rejects_tampered_body_wrong_secret_and_garbage():
    h = f"t={T},v1={sign()}"
    assert not verify_webhook_signature(SECRET, BODY + " ", h, now=T)
    assert not verify_webhook_signature("other", BODY, h, now=T)
    assert not verify_webhook_signature(SECRET, BODY, None, now=T)
    assert not verify_webhook_signature(SECRET, BODY, "", now=T)
    assert not verify_webhook_signature(SECRET, BODY, f"t={T}", now=T)
    assert not verify_webhook_signature(SECRET, BODY, f"v1={sign()}", now=T)
    assert not verify_webhook_signature(SECRET, BODY, f"t=abc,v1={sign()}", now=T)


def test_tolerance():
    h = f"t={T},v1={sign()}"
    assert not verify_webhook_signature(SECRET, BODY, h, now=T + 301)
    assert not verify_webhook_signature(SECRET, BODY, h, now=T - 301)
    assert verify_webhook_signature(SECRET, BODY, h, now=T + 600, tolerance=600)


def test_multiple_v1_values_any_matches():
    h = f"t={T}, v1=deadbeef, v1={sign()}"
    assert verify_webhook_signature(SECRET, BODY, h, now=T)


def test_construct_event():
    ev = construct_webhook_event(SECRET, BODY, f"t={T},v1={sign()}", now=T)
    assert ev["type"] == "order.filled"
    with pytest.raises(WebhookSignatureError):
        construct_webhook_event(SECRET, BODY, f"t={T},v1=00", now=T)
